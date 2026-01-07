#!/usr/bin/env python3
"""
Analysis Service API for PII Analyzer

Provides REST endpoints for controlling PII analysis:
- Start/Stop analysis
- Check status
- Generate reports
- Clear results
"""

import os
import sys
import json
import signal
import threading
import multiprocessing
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.database.db_utils import get_database
from src.core.file_discovery import scan_directory, get_file_statistics
from src.core.worker_management import process_files_parallel, calculate_optimal_workers
from src.core.pii_analyzer_adapter import analyze_file

logger = logging.getLogger('analysis_service')


class AnalysisState(Enum):
    """Analysis state enumeration"""
    IDLE = "idle"
    SCANNING = "scanning"
    PROCESSING = "processing"
    STOPPING = "stopping"
    COMPLETED = "completed"
    ERROR = "error"


class AnalysisService:
    """
    Singleton service for managing PII analysis operations.
    Runs analysis in background threads/processes.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    # Default supported file extensions
    DEFAULT_EXTENSIONS = {
        '.txt', '.pdf', '.docx', '.doc', '.rtf',
        '.xlsx', '.xls', '.csv', '.tsv',
        '.pptx', '.ppt',
        '.json', '.xml', '.html', '.htm',
        '.md', '.log', '.eml', '.msg'
    }
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._state = AnalysisState.IDLE
        self._current_job_id: Optional[int] = None
        self._analysis_thread: Optional[threading.Thread] = None
        self._stop_requested = threading.Event()
        self._progress: Dict[str, Any] = {}
        self._error_message: Optional[str] = None
        self._db_path: str = os.environ.get('PII_DB_PATH', '/app/db/pii_results.db')
        self._data_path: str = os.environ.get('PII_DATA_PATH', '/data')
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
        
        # Configuration - optimized for high-performance systems
        self._workers = int(os.environ.get('PII_WORKERS', calculate_optimal_workers()))
        self._batch_size = int(os.environ.get('PII_BATCH_SIZE', 50))
        self._threshold = float(os.environ.get('PII_THRESHOLD', 0.7))
        self._file_size_limit = int(os.environ.get('PII_FILE_SIZE_LIMIT', 100)) * 1024 * 1024
        
        logger.info(f"AnalysisService initialized: db_path={self._db_path}, data_path={self._data_path}")
        logger.info(f"Workers: {self._workers}, Batch size: {self._batch_size}, Threshold: {self._threshold}")
    
    @property
    def state(self) -> AnalysisState:
        return self._state
    
    @property
    def is_running(self) -> bool:
        return self._state in (AnalysisState.SCANNING, AnalysisState.PROCESSING)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current analysis status"""
        status = {
            'state': self._state.value,
            'job_id': self._current_job_id,
            'is_running': self.is_running,
            'can_start': self._state == AnalysisState.IDLE,
            'can_stop': self.is_running,
            'data_path': self._data_path,
            'db_path': self._db_path,
            'error': self._error_message,
        }
        
        # Add timing info
        if self._start_time:
            status['start_time'] = self._start_time.isoformat()
            if self._end_time:
                status['end_time'] = self._end_time.isoformat()
                status['duration_seconds'] = (self._end_time - self._start_time).total_seconds()
            else:
                status['duration_seconds'] = (datetime.now() - self._start_time).total_seconds()
        
        # Add progress info if available
        if self._progress:
            status['progress'] = self._progress
        
        # Add database stats if we have a job
        if self._current_job_id and os.path.exists(self._db_path):
            try:
                db = get_database(self._db_path)
                stats = get_file_statistics(db, self._current_job_id)
                total = stats.get('total', 0)
                completed = stats.get('completed', 0)
                pending = stats.get('pending', 0)
                processing = stats.get('processing', 0)
                error = stats.get('error', 0)
                
                status['files'] = {
                    'total': total,
                    'completed': completed,
                    'pending': pending,
                    'processing': processing,
                    'error': error,
                    'progress_percent': round((completed + error) / total * 100, 1) if total > 0 else 0
                }
            except Exception as e:
                logger.error(f"Error getting database stats: {e}")
        
        return status
    
    def start_analysis(self) -> Dict[str, Any]:
        """Start a new analysis run"""
        if self.is_running:
            return {
                'success': False,
                'error': 'Analysis is already running',
                'state': self._state.value
            }
        
        # Verify data path exists
        if not os.path.isdir(self._data_path):
            return {
                'success': False,
                'error': f'Data path does not exist: {self._data_path}',
                'state': self._state.value
            }
        
        # Reset state
        self._stop_requested.clear()
        self._error_message = None
        self._progress = {}
        self._start_time = datetime.now()
        self._end_time = None
        
        # Start analysis in background thread
        self._analysis_thread = threading.Thread(
            target=self._run_analysis,
            daemon=True
        )
        self._analysis_thread.start()
        
        return {
            'success': True,
            'message': 'Analysis started',
            'state': self._state.value
        }
    
    def stop_analysis(self) -> Dict[str, Any]:
        """Stop the current analysis"""
        if not self.is_running:
            return {
                'success': False,
                'error': 'No analysis is running',
                'state': self._state.value
            }
        
        logger.info("Stop requested for analysis")
        self._state = AnalysisState.STOPPING
        self._stop_requested.set()
        
        return {
            'success': True,
            'message': 'Stop requested. Analysis will stop after current batch completes.',
            'state': self._state.value
        }
    
    def clear_results(self) -> Dict[str, Any]:
        """Clear all analysis results"""
        if self.is_running:
            return {
                'success': False,
                'error': 'Cannot clear results while analysis is running',
                'state': self._state.value
            }
        
        try:
            # Remove the database file
            if os.path.exists(self._db_path):
                os.remove(self._db_path)
                logger.info(f"Removed database: {self._db_path}")
            
            # Reset state
            self._state = AnalysisState.IDLE
            self._current_job_id = None
            self._progress = {}
            self._error_message = None
            self._start_time = None
            self._end_time = None
            
            return {
                'success': True,
                'message': 'Results cleared successfully',
                'state': self._state.value
            }
        except Exception as e:
            logger.error(f"Error clearing results: {e}")
            return {
                'success': False,
                'error': str(e),
                'state': self._state.value
            }
    
    def export_results_json(self) -> Dict[str, Any]:
        """Export results as JSON"""
        if not os.path.exists(self._db_path):
            return {
                'success': False,
                'error': 'No results to export'
            }
        
        try:
            db = get_database(self._db_path)
            
            # Get the most recent job
            jobs = db.get_all_jobs()
            if not jobs:
                return {
                    'success': False,
                    'error': 'No jobs found'
                }
            
            job_id = jobs[0]['job_id']
            data = db.export_to_json(job_id)
            
            return {
                'success': True,
                'data': data,
                'job_id': job_id
            }
        except Exception as e:
            logger.error(f"Error exporting results: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _run_analysis(self):
        """Background thread for running analysis"""
        try:
            logger.info(f"Starting analysis of {self._data_path}")
            self._state = AnalysisState.SCANNING
            
            # Connect to database
            db = get_database(self._db_path)
            
            # Create a new job
            self._current_job_id = db.create_job(self._data_path)
            logger.info(f"Created job {self._current_job_id}")
            
            # Scan directory for files
            def scan_callback(state):
                if self._stop_requested.is_set():
                    return
                if state['type'] == 'progress':
                    self._progress['files_scanned'] = state.get('files_scanned', 0)
                    logger.debug(f"Scanned {state.get('files_scanned', 0)} files...")
            
            result = scan_directory(
                db,
                self._current_job_id,
                self._data_path,
                extensions=self.DEFAULT_EXTENSIONS,
                progress_callback=scan_callback
            )
            
            if self._stop_requested.is_set():
                logger.info("Analysis stopped during scanning")
                self._state = AnalysisState.IDLE
                return
            
            logger.info(f"Scan complete: {result['added']} files added")
            self._progress['files_discovered'] = result['added']
            
            # Get stats
            stats = get_file_statistics(db, self._current_job_id)
            pending_count = stats.get('pending', 0)
            
            if pending_count == 0:
                logger.info("No files to process")
                self._state = AnalysisState.COMPLETED
                self._end_time = datetime.now()
                return
            
            # Switch to processing state
            self._state = AnalysisState.PROCESSING
            db.update_job_status(self._current_job_id, 'running')
            
            # Prepare settings
            settings = {
                'threshold': self._threshold,
                'file_size_limit': self._file_size_limit,
            }
            
            # Progress callback for processing
            def progress_callback(state):
                if self._stop_requested.is_set():
                    return
                if state['type'] == 'file_completed':
                    completed = db.get_completed_count_for_job(self._current_job_id)
                    self._progress['files_completed'] = completed
            
            # Process files
            logger.info(f"Starting processing with {self._workers} workers")
            result = process_files_parallel(
                db,
                self._current_job_id,
                analyze_file,
                max_workers=self._workers,
                batch_size=self._batch_size,
                settings=settings,
                progress_callback=progress_callback,
                stop_event=self._stop_requested
            )
            
            # Update final status
            if self._stop_requested.is_set():
                db.update_job_status(self._current_job_id, 'interrupted')
                self._state = AnalysisState.IDLE
                logger.info("Analysis stopped by user")
            elif result.get('status') == 'completed':
                db.update_job_status(self._current_job_id, 'completed')
                self._state = AnalysisState.COMPLETED
                logger.info("Analysis completed successfully")
            else:
                db.update_job_status(self._current_job_id, 'interrupted')
                self._state = AnalysisState.IDLE
                logger.info("Analysis interrupted")
            
            self._end_time = datetime.now()
            
        except Exception as e:
            logger.exception(f"Error during analysis: {e}")
            self._state = AnalysisState.ERROR
            self._error_message = str(e)
            self._end_time = datetime.now()


# Global service instance
_analysis_service: Optional[AnalysisService] = None


def get_analysis_service() -> AnalysisService:
    """Get the global analysis service instance"""
    global _analysis_service
    if _analysis_service is None:
        _analysis_service = AnalysisService()
    return _analysis_service

