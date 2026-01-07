#!/usr/bin/env python3
"""
Worker Management Module for PII Analyzer
Provides functions to manage parallel processing of files
using the database for tracking and coordination

Performance optimized for high-core count systems with NFS storage.
"""

import concurrent.futures
import time
import logging
import multiprocessing
import queue
import threading
import os
import psutil
import setproctitle
import math
from datetime import datetime
from typing import Callable, List, Dict, Any, Optional, Tuple

from src.database.db_utils import get_database, PIIDatabase

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - [%(process)d] %(message)s'
)
logger = logging.getLogger('worker_management')

# Thread-local storage for database connections
thread_local = threading.local()

# Global OCR semaphore to limit OCR processes
# Will be initialized during process_files_parallel
OCR_SEMAPHORE = None

# Target CPU utilization (percentage)
TARGET_CPU_UTILIZATION = 70  # Reduced from 85% to 70%
MIN_CPU_UTILIZATION = 60     # Adjusted down to match new target
MAX_CPU_UTILIZATION = 80     # Reduced from 95% to 80%

# Dynamic scaling parameters
MAX_BATCH_SIZE = 50          # Smaller batches for better progress tracking
MIN_BATCH_SIZE = 20          # Minimum batch size
SCALING_INTERVAL = 30        # Check utilization every 30 seconds (faster response)
WORKER_STEP_SIZE = 10        # Normal worker adjustment step (smaller for stability)
WORKER_EMERGENCY_REDUCTION = 20  # Larger reduction when system is overloaded
BATCH_STEP_SIZE = 10         # Increase/decrease batch size by this amount

# Load average thresholds (relative to CPU count)
# For a 32-core system, MAX_LOAD_FACTOR of 1.5 means alert at load avg > 48
MAX_LOAD_FACTOR = 1.5        # Maximum acceptable load average as a factor of CPU count
CRITICAL_LOAD_FACTOR = 2.0   # Critical load threshold that triggers emergency measures

# Worker timeout and monitoring
WORKER_TIMEOUT_SECONDS = 180  # 3 minutes per file (balance between timeout detection and allowing complex files)
STALLED_WORKER_CHECK_INTERVAL = 30  # Check for stalled workers every 30 seconds
MAX_CONSECUTIVE_ERRORS = 50  # Stop batch if too many consecutive errors (raised for timeout bursts)

def get_thread_db(db_path: str) -> PIIDatabase:
    """
    Get a thread-local database connection.
    SQLite connections can only be used in the thread they were created in.
    
    Args:
        db_path: Path to the database file
        
    Returns:
        Thread-specific database connection
    """
    if not hasattr(thread_local, "db"):
        thread_local.db = get_database(db_path)
    return thread_local.db

class SafeQueue:
    """Thread-safe queue to track results and communicate between threads."""
    
    def __init__(self):
        self.queue = queue.Queue()
        self.processed = 0
        self.errors = 0
        self.lock = threading.Lock()
    
    def add_processed(self):
        """Increment processed count."""
        with self.lock:
            self.processed += 1
    
    def add_error(self):
        """Increment error count."""
        with self.lock:
            self.errors += 1
    
    def get_stats(self) -> Tuple[int, int]:
        """Get current statistics."""
        with self.lock:
            return self.processed, self.errors

def get_system_utilization() -> Dict[str, float]:
    """
    Get current system utilization metrics.
    
    Returns:
        Dictionary with CPU and memory utilization percentages and load average
    """
    # Get CPU utilization (averaged over 0.5 seconds for faster response)
    cpu_percent = psutil.cpu_percent(interval=0.5)
    
    # Get memory utilization
    memory = psutil.virtual_memory()
    memory_percent = memory.percent
    
    # Get system load average
    load_avg = os.getloadavg()
    
    # Get CPU count for load average context
    cpu_count = psutil.cpu_count(logical=True)
    
    # Calculate load factor (load average relative to CPU count)
    load_factor_1min = load_avg[0] / cpu_count if cpu_count else 0
    
    return {
        'cpu_percent': cpu_percent,
        'memory_percent': memory_percent,
        'load_avg_1min': load_avg[0],
        'load_avg_5min': load_avg[1],
        'load_avg_15min': load_avg[2],
        'cpu_count': cpu_count,
        'load_factor': load_factor_1min
    }

def calculate_optimal_workers(current_workers: Optional[int] = None, utilization_info: Optional[Dict[str, float]] = None) -> int:
    """
    Calculate the optimal number of worker processes based on system resources.
    If current_workers and utilization_info are provided, will adjust based on current performance.
    
    Optimized for systems with NFS storage where I/O latency is significant.
    
    Args:
        current_workers: Current number of workers (if already running)
        utilization_info: Current system utilization metrics
        
    Returns:
        Optimal number of worker processes
    """
    try:
        # Get CPU cores and memory
        cpu_count = psutil.cpu_count(logical=True)
        memory_gb = psutil.virtual_memory().total / (1024 * 1024 * 1024)
        
        # If we have current utilization data and workers, use it to adjust
        if current_workers is not None and utilization_info is not None:
            current_cpu = utilization_info.get('cpu_percent', 0)
            current_memory = utilization_info.get('memory_percent', 0)
            current_load_factor = utilization_info.get('load_factor', 0)
            
            # Check for critical system load - emergency reduction
            if current_load_factor > CRITICAL_LOAD_FACTOR:
                # Aggressive reduction to quickly relieve system pressure
                reduction = min(WORKER_EMERGENCY_REDUCTION, current_workers // 3)
                new_workers = max(8, current_workers - reduction)
                logger.warning(f"CRITICAL SYSTEM LOAD: Load factor {current_load_factor:.2f} exceeds threshold {CRITICAL_LOAD_FACTOR}. Aggressively reducing workers from {current_workers} to {new_workers}")
                return new_workers
                
            # Check for high system load - standard reduction
            if current_load_factor > MAX_LOAD_FACTOR:
                # Standard reduction to relieve system pressure
                reduction = min(WORKER_STEP_SIZE * 2, current_workers // 5)
                new_workers = max(8, current_workers - reduction)
                logger.warning(f"HIGH SYSTEM LOAD: Load factor {current_load_factor:.2f} exceeds threshold {MAX_LOAD_FACTOR}. Reducing workers from {current_workers} to {new_workers}")
                return new_workers
            
            # If we're below target CPU utilization and system load is acceptable, increase workers
            if current_cpu < MIN_CPU_UTILIZATION and current_memory < 80 and current_load_factor < 0.8:
                # Increase gradually to avoid overshooting
                adjustment = WORKER_STEP_SIZE
                new_workers = current_workers + adjustment
                logger.info(f"CPU utilization {current_cpu}% is below target {TARGET_CPU_UTILIZATION}%, increasing workers from {current_workers} to {new_workers}")
                return new_workers
                
            # If we're above max CPU utilization or memory pressure, decrease workers
            elif current_cpu > MAX_CPU_UTILIZATION or current_memory > 90:
                # Decrease to avoid system overload
                adjustment = WORKER_STEP_SIZE
                new_workers = max(8, current_workers - adjustment)
                logger.info(f"System pressure detected (CPU: {current_cpu}%, Memory: {current_memory}%), decreasing workers from {current_workers} to {new_workers}")
                return new_workers
                
            # If we're within acceptable range, maintain current workers
            else:
                logger.debug(f"Current CPU utilization {current_cpu}% is in acceptable range, maintaining {current_workers} workers")
                return current_workers
        
        # For 96+ core high-memory systems
        if cpu_count >= 96:
            # Use 50% of available cores to avoid context switching overhead
            base_workers = int(cpu_count * 0.5)
            
            # Calculate workers based on memory (assume ~1GB per worker with Presidio)
            max_by_memory = int((memory_gb * 0.7) / 1.0)
            
            optimal_workers = min(base_workers, max_by_memory, 64)
            
            logger.info(f"High-end system detected. Using {optimal_workers} workers (CPU: {cpu_count}, Memory: {memory_gb:.1f}GB)")
            return optimal_workers
        
        # For 32-64 core systems (like our target 32-core server)
        elif cpu_count >= 32:
            # For I/O bound work with NFS, use fewer workers to avoid network congestion
            # Each worker does: NFS read -> Tika request -> PII analysis -> DB write
            # With 8 Tika instances, optimal is around 16-24 workers
            base_workers = min(24, int(cpu_count * 0.75))
            
            # Memory check (assume ~1GB per worker)
            max_by_memory = int((memory_gb * 0.6) / 1.0)
            
            optimal_workers = min(base_workers, max_by_memory)
            
            logger.info(f"32+ core system detected. Using {optimal_workers} workers (CPU: {cpu_count}, Memory: {memory_gb:.1f}GB)")
            return optimal_workers
        
        # For 8-32 core systems
        elif cpu_count >= 8:
            # Use 80% of cores
            base_workers = max(4, int(cpu_count * 0.8))
            max_by_memory = int((memory_gb * 0.6) / 1.0)
            optimal_workers = min(base_workers, max_by_memory)
            
            logger.info(f"Mid-range system. Using {optimal_workers} workers (CPU: {cpu_count}, Memory: {memory_gb:.1f}GB)")
            return optimal_workers
        
        # Standard calculation for smaller systems
        else:
            # Use most of available cores for smaller systems
            base_workers = max(2, int(cpu_count * 0.9))
            max_by_memory = int((memory_gb * 0.6) / 1.0)
            optimal_workers = min(base_workers, max_by_memory)
            
            logger.info(f"Small system. Using {optimal_workers} workers (CPU: {cpu_count}, Memory: {memory_gb:.1f}GB)")
            return optimal_workers
    
    except Exception as e:
        logger.warning(f"Error calculating optimal workers: {e}, using fallback value")
        # Conservative fallback
        return 16

def process_files_parallel(
    db: PIIDatabase,
    job_id: int,
    processing_func: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    max_workers: Optional[int] = None,
    batch_size: int = 50,  # Smaller batches for better progress tracking
    max_files: Optional[int] = None,
    settings: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    enable_dynamic_scaling: bool = True,  # Enable dynamic scaling by default
    stop_event: Optional[threading.Event] = None  # Optional stop event for graceful shutdown
) -> Dict[str, Any]:
    """
    Process files in parallel using database to track progress.
    
    Args:
        db: Database connection
        job_id: Job ID to process
        processing_func: Function that processes a single file
        max_workers: Maximum number of worker processes (None for auto)
        batch_size: Number of files to fetch at once
        max_files: Maximum number of files to process (None for all)
        settings: Additional settings to pass to processing function
        progress_callback: Optional callback function to report progress
        enable_dynamic_scaling: Whether to dynamically adjust workers and batch size
        stop_event: Optional threading.Event to signal graceful shutdown
        
    Returns:
        Dictionary with processing statistics
    """
    if not max_workers:
        # Auto-determine based on system resources
        max_workers = calculate_optimal_workers()
    
    if settings is None:
        settings = {}
    
    # Get the database path for worker processes
    db_path = db.db_path
    
    # Set process title for main process
    setproctitle.setproctitle(f"pii-main-{os.getpid()}")
    
    start_time = time.time()
    stats_queue = SafeQueue()
    files_remaining = True
    processed_count = 0
    error_count = 0
    
    # Print system info
    cpu_count = psutil.cpu_count(logical=True)
    memory_gb = psutil.virtual_memory().total / (1024 * 1024 * 1024)
    logger.info(f"System info: {cpu_count} CPU cores, {memory_gb:.1f}GB memory")
    logger.info(f"Starting parallel processing with {max_workers} worker processes and batch size {batch_size}")
    
    # Initialize scaling variables
    current_batch_size = batch_size
    current_max_workers = max_workers
    last_scaling_check = time.time()
    scaling_stats = {
        'adjustments': 0,
        'worker_increases': 0,
        'worker_decreases': 0,
        'batch_increases': 0,
        'batch_decreases': 0
    }
    
    # Create a process pool with fixed number of workers
    # Use ProcessPoolExecutor for true parallelism
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        while files_remaining and (max_files is None or processed_count < max_files):
            # Check for stop request
            if stop_event is not None and stop_event.is_set():
                logger.info("Stop event detected, stopping file processing")
                files_remaining = False
                break
            # Dynamic scaling: periodically check and adjust resources
            if enable_dynamic_scaling and time.time() - last_scaling_check > SCALING_INTERVAL:
                # Check current CPU and memory utilization
                utilization = get_system_utilization()
                cpu_percent = utilization['cpu_percent']
                memory_percent = utilization['memory_percent']
                load_factor = utilization.get('load_factor', 0)
                load_avg_1min = utilization.get('load_avg_1min', 0)
                
                # Log current utilization
                logger.info(f"Current utilization - CPU: {cpu_percent:.1f}%, Memory: {memory_percent:.1f}%, Load avg: {load_avg_1min:.2f} (factor: {load_factor:.2f}), Workers: {current_max_workers}, Batch size: {current_batch_size}")
                
                # Emergency check for critical system load
                if load_factor > CRITICAL_LOAD_FACTOR:
                    # Immediately reduce batch size to minimum
                    if current_batch_size > MIN_BATCH_SIZE:
                        logger.warning(f"CRITICAL LOAD DETECTED ({load_avg_1min:.2f}), reducing batch size to minimum {MIN_BATCH_SIZE}")
                        current_batch_size = MIN_BATCH_SIZE
                        scaling_stats['batch_decreases'] += 1
                
                # Adjust workers if needed
                new_workers = calculate_optimal_workers(current_max_workers, utilization)
                if new_workers != current_max_workers:
                    # We can't change the pool size dynamically, but we'll use this for the next batch
                    logger.info(f"Adjusting worker count from {current_max_workers} to {new_workers} for next execution")
                    scaling_stats['adjustments'] += 1
                    if new_workers > current_max_workers:
                        scaling_stats['worker_increases'] += 1
                    else:
                        scaling_stats['worker_decreases'] += 1
                    current_max_workers = new_workers
                
                # Adjust batch size based on CPU utilization and load
                if load_factor < 0.8 and cpu_percent < MIN_CPU_UTILIZATION and memory_percent < 80:
                    # Increase batch size to process more files at once
                    new_batch_size = min(MAX_BATCH_SIZE, current_batch_size + BATCH_STEP_SIZE)
                    if new_batch_size != current_batch_size:
                        logger.info(f"Increasing batch size from {current_batch_size} to {new_batch_size}")
                        current_batch_size = new_batch_size
                        scaling_stats['batch_increases'] += 1
                elif load_factor > MAX_LOAD_FACTOR or cpu_percent > MAX_CPU_UTILIZATION or memory_percent > 90:
                    # Decrease batch size to reduce system pressure
                    new_batch_size = max(MIN_BATCH_SIZE, current_batch_size - BATCH_STEP_SIZE)
                    if new_batch_size != current_batch_size:
                        logger.info(f"Decreasing batch size from {current_batch_size} to {new_batch_size}")
                        current_batch_size = new_batch_size
                        scaling_stats['batch_decreases'] += 1
                
                # Update last check time
                last_scaling_check = time.time()
            
            # Get batch of pending files using current batch size
            limit = min(current_batch_size, max_files - processed_count if max_files else current_batch_size)
            pending_files = db.get_pending_files(job_id, limit=limit)
            
            if not pending_files:
                files_remaining = False
                break
            
            # Log batch information with sample file paths
            batch_start_timestamp = datetime.now().isoformat()
            sample_files = [os.path.basename(f[1]) for f in pending_files[:3]]
            logger.info(f"[{batch_start_timestamp}] Processing batch of {len(pending_files)} files. Sample: {sample_files}")
            
            # Track file submissions for monitoring
            submitted_files = {}
            
            # Submit jobs to process pool
            futures = []
            for i, (file_id, file_path) in enumerate(pending_files):
                # Mark file as processing
                if db.mark_file_processing(file_id):
                    # Assign a worker ID for tracking
                    worker_settings = settings.copy()
                    worker_settings['worker_id'] = i
                    
                    future = executor.submit(
                        process_single_file_process_safe,
                        file_id,
                        file_path,
                        db_path,
                        job_id,
                        worker_settings
                    )
                    futures.append(future)
                    submitted_files[future] = {
                        'file_id': file_id,
                        'file_path': file_path,
                        'submitted_at': time.time()
                    }
            
            # Wait for the batch to complete with timeout monitoring
            batch_start_time = time.time()
            batch_files_processed = 0
            batch_files_succeeded = 0
            batch_files_failed = 0
            stop_requested = False
            consecutive_errors = 0
            slow_files = []
            
            for future in concurrent.futures.as_completed(futures, timeout=WORKER_TIMEOUT_SECONDS * 2):
                # Check for stop request during batch processing
                if stop_event is not None and stop_event.is_set():
                    stop_requested = True
                    logger.info("Stop event detected during batch processing")
                    # Continue processing to allow graceful completion of already-started work
                    # but don't submit new batches
                
                try:
                    # Get file info for this future
                    file_info = submitted_files.get(future, {})
                    file_path = file_info.get('file_path', 'unknown')
                    file_id = file_info.get('file_id', 0)
                    submitted_at = file_info.get('submitted_at', batch_start_time)
                    
                    result = future.result(timeout=WORKER_TIMEOUT_SECONDS)
                    batch_files_processed += 1
                    
                    # Calculate processing time
                    file_processing_time = time.time() - submitted_at
                    
                    # Log slow files (> 30 seconds)
                    if file_processing_time > 30:
                        slow_files.append({
                            'path': os.path.basename(file_path),
                            'time': file_processing_time
                        })
                        logger.warning(f"SLOW FILE: {os.path.basename(file_path)} took {file_processing_time:.1f}s")
                    
                    if result.get('success', False):
                        # Update the database with results
                        db.store_file_results(
                            result['file_id'], 
                            result['processing_time'], 
                            result.get('entities', []), 
                            result.get('metadata', {})
                        )
                        db.mark_file_completed(result['file_id'], job_id)
                        stats_queue.add_processed()
                        processed_count += 1
                        batch_files_succeeded += 1
                        consecutive_errors = 0  # Reset error counter on success
                        
                        # Log individual file completion for debugging
                        entity_count = len(result.get('entities', []))
                        logger.debug(f"Completed: {os.path.basename(file_path)} - {entity_count} entities in {file_processing_time:.1f}s")
                    else:
                        # Mark as error
                        error_msg = result.get('error_message', 'Unknown error')
                        db.mark_file_error(result['file_id'], job_id, error_msg)
                        stats_queue.add_error()
                        error_count += 1
                        batch_files_failed += 1
                        consecutive_errors += 1
                        
                        # Log error details
                        logger.warning(f"Failed: {os.path.basename(file_path)} - {error_msg[:100]}")
                    
                    # Call progress callback if provided
                    if progress_callback:
                        progress_callback({
                            'type': 'file_completed' if result.get('success', False) else 'file_error',
                            'file_id': result.get('file_id'),
                            'file_path': result.get('file_path'),
                            'entities': result.get('entities', []),
                            'error': result.get('error_message') if not result.get('success', False) else None
                        })
                    
                    # Log progress every 10 files or every 30 seconds
                    total_processed = processed_count + error_count
                    if total_processed % 10 == 0 and total_processed > 0:
                        elapsed = time.time() - start_time
                        rate = total_processed / elapsed if elapsed > 0 else 0
                        mem = psutil.virtual_memory()
                        logger.info(f"Progress: {total_processed} files in {elapsed:.1f}s ({rate:.2f}/sec) | Memory: {mem.percent:.1f}% | Errors: {error_count}")
                    
                    # Check for too many consecutive errors
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logger.error(f"Too many consecutive errors ({consecutive_errors}), stopping batch")
                        stop_requested = True
                        
                except concurrent.futures.TimeoutError:
                    # Handle timeout - file took too long
                    file_info = submitted_files.get(future, {})
                    file_path = file_info.get('file_path', 'unknown')
                    file_id = file_info.get('file_id', 0)
                    
                    logger.error(f"TIMEOUT: {os.path.basename(file_path)} exceeded {WORKER_TIMEOUT_SECONDS}s")
                    
                    if file_id:
                        db.mark_file_error(file_id, job_id, f"Processing timeout ({WORKER_TIMEOUT_SECONDS}s)")
                    
                    error_count += 1
                    batch_files_failed += 1
                    consecutive_errors += 1
                    
                except Exception as e:
                    logger.error(f"Worker process error: {e}")
                    error_count += 1
                    batch_files_failed += 1
                    consecutive_errors += 1
                    
                    # Call progress callback for errors if provided
                    if progress_callback:
                        progress_callback({
                            'type': 'file_error',
                            'error': str(e)
                        })
            
            # Log detailed batch statistics
            batch_elapsed = time.time() - batch_start_time
            batch_rate = batch_files_processed / batch_elapsed if batch_elapsed > 0 else 0
            success_rate = (batch_files_succeeded / batch_files_processed * 100) if batch_files_processed > 0 else 0
            
            logger.info(f"Batch completed: {batch_files_processed} files ({batch_files_succeeded} OK, {batch_files_failed} failed) in {batch_elapsed:.1f}s ({batch_rate:.2f}/sec, {success_rate:.0f}% success)")
            
            # Log slow files summary if any
            if slow_files:
                avg_slow_time = sum(f['time'] for f in slow_files) / len(slow_files)
                logger.warning(f"Slow files in batch: {len(slow_files)}, avg time: {avg_slow_time:.1f}s")
            
            # If stop was requested during this batch, exit the loop
            if stop_requested:
                files_remaining = False
                break
            
            # Check for resource exhaustion
            mem = psutil.virtual_memory()
            if mem.percent > 90:
                logger.warning(f"Memory pressure detected ({mem.percent}% used), reducing batch size")
                current_batch_size = max(MIN_BATCH_SIZE, current_batch_size // 2)  # Maintain minimum batch size of 50
    
    # Update job status
    elapsed = time.time() - start_time
    rate = processed_count / elapsed if elapsed > 0 else 0
    
    # Log scaling statistics
    if enable_dynamic_scaling:
        logger.info(f"Dynamic scaling summary: Total adjustments: {scaling_stats['adjustments']}")
        logger.info(f"Worker increases: {scaling_stats['worker_increases']}, Worker decreases: {scaling_stats['worker_decreases']}")
        logger.info(f"Batch increases: {scaling_stats['batch_increases']}, Batch decreases: {scaling_stats['batch_decreases']}")
    
    if not files_remaining:
        db.update_job_status(job_id, 'completed')
        logger.info(f"Job completed: processed {processed_count} files ({error_count} errors) in {elapsed:.2f}s ({rate:.2f} files/sec)")
    else:
        db.update_job_status(job_id, 'interrupted')
        logger.info(f"Job interrupted: processed {processed_count} files ({error_count} errors) in {elapsed:.2f}s ({rate:.2f} files/sec)")
    
    return {
        'processed': processed_count,
        'errors': error_count,
        'elapsed': elapsed,
        'rate': rate,
        'status': 'completed' if not files_remaining else 'interrupted',
        'scaling_stats': scaling_stats if enable_dynamic_scaling else {}
    }

def process_single_file_process_safe(
    file_id: int,
    file_path: str,
    db_path: str,
    job_id: int,
    settings: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process a single file safely in a separate process.
    This function is the entry point for ProcessPoolExecutor workers.
    
    Args:
        file_id: ID of the file to process
        file_path: Path to the file
        db_path: Path to the database
        job_id: ID of the current job
        settings: Processing settings
        
    Returns:
        Processing result dictionary
    """
    try:
        # Import the pii_analyzer_adapter in the worker process
        from src.core.pii_analyzer_adapter import analyze_file
        
        # Process the file
        start_time = time.time()
        
        # Set process title for identifying in monitoring tools
        setproctitle.setproctitle(f"pii-worker-{settings.get('worker_id', os.getpid())}")
        
        result = analyze_file(file_path, settings)
        
        # Add file ID and path to result for tracking
        result['file_id'] = file_id
        result['file_path'] = file_path
        
        # Add timing data
        processing_time = time.time() - start_time
        result['processing_time'] = processing_time
        
        return result
    
    except Exception as e:
        # Catch any exception and return a standardized error result
        logger.error(f"Error in worker process for file {file_path}: {str(e)}")
        return {
            'file_id': file_id,
            'file_path': file_path,
            'success': False,
            'error_message': f"Worker process exception: {str(e)}",
            'processing_time': time.time() - start_time if 'start_time' in locals() else 0
        }

def process_single_file_thread_safe(
    file_id: int,
    file_path: str,
    db_path: str,
    job_id: int,
    processing_func: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    settings: Dict[str, Any],
    stats_queue: SafeQueue
) -> Dict[str, Any]:
    """
    Process a single file safely in a worker thread.
    This function is the entry point for ThreadPoolExecutor workers.
    
    Args:
        file_id: ID of the file to process
        file_path: Path to the file
        db_path: Path to the database
        job_id: ID of the current job
        processing_func: Function to process the file
        settings: Processing settings
        stats_queue: Queue for tracking statistics
        
    Returns:
        Processing result
    """
    # Get thread-local database connection
    db = get_thread_db(db_path)
    
    try:
        # Process the file
        result = process_single_file(file_id, file_path, db, job_id, processing_func, settings)
        
        # Update statistics
        if result.get('success', False):
            stats_queue.add_processed()
        else:
            stats_queue.add_error()
        
        return result
    
    except Exception as e:
        # Log the error
        logger.error(f"Error processing file {file_path}: {e}")
        
        # Mark as error in the database
        db.mark_file_error(file_id, job_id, str(e))
        
        # Update statistics
        stats_queue.add_error()
        
        # Return error result
        return {
            'file_id': file_id,
            'file_path': file_path,
            'success': False,
            'error_message': str(e)
        }

def process_single_file(
    file_id: int,
    file_path: str,
    db: PIIDatabase,
    job_id: int,
    processing_func: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    settings: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process a single file, handling database updates.
    
    Args:
        file_id: ID of the file to process
        file_path: Path to the file
        db: Database connection
        job_id: ID of the current job
        processing_func: Function to process the file
        settings: Processing settings
        
    Returns:
        Processing result dictionary
    """
    # Mark file as processing
    if not db.mark_file_processing(file_id):
        return {
            'file_id': file_id,
            'file_path': file_path,
            'success': False,
            'error_message': "Could not mark file as processing"
        }
    
    try:
        # Measure processing time
        start_time = time.time()
        
        # Process the file
        result = processing_func(file_path, settings)
        
        # Add file ID to result
        result['file_id'] = file_id
        result['file_path'] = file_path
        
        # Calculate processing time
        processing_time = time.time() - start_time
        result['processing_time'] = processing_time
        
        # Update the database
        if result.get('success', False):
            # Store entities and mark as completed
            db.store_file_results(
                file_id, 
                processing_time, 
                result.get('entities', []), 
                result.get('metadata', {})
            )
            db.mark_file_completed(file_id, job_id)
        else:
            # Mark as error
            db.mark_file_error(
                file_id, 
                job_id, 
                result.get('error_message', 'Unknown error')
            )
        
        return result
    
    except Exception as e:
        # Log the error
        logger.error(f"Error processing file {file_path}: {e}")
        
        # Mark as error in the database
        db.mark_file_error(file_id, job_id, str(e))
        
        # Return error result
        return {
            'file_id': file_id,
            'file_path': file_path,
            'success': False,
            'error_message': str(e)
        }

def estimate_completion_time(
    db: PIIDatabase,
    job_id: int
) -> Dict[str, Any]:
    """
    Estimate remaining time for job completion based on
    current processing rate.
    
    Args:
        db: Database connection
        job_id: Job ID to estimate
        
    Returns:
        Dictionary with estimation information
    """
    # Get job information
    job = db.get_job(job_id)
    if not job:
        return {
            'status': 'error',
            'message': f"Job {job_id} not found"
        }
    
    # Get file counts
    total_files = job.get('total_files', 0)
    processed_files = job.get('processed_files', 0)
    error_files = job.get('error_files', 0)
    
    # Calculate remaining files
    remaining_files = total_files - processed_files - error_files
    
    # Check if job is still running
    if job.get('status') != 'running':
        return {
            'status': job.get('status'),
            'total_files': total_files,
            'processed_files': processed_files,
            'error_files': error_files,
            'remaining_files': remaining_files,
            'message': f"Job is not running, status is {job.get('status')}"
        }
    
    # Calculate processing rate
    start_time = job.get('start_time')
    last_updated = job.get('last_updated')
    
    if not start_time or not last_updated or processed_files == 0:
        return {
            'status': 'running',
            'total_files': total_files,
            'processed_files': processed_files,
            'error_files': error_files,
            'remaining_files': remaining_files,
            'message': "Insufficient data to estimate completion time"
        }
    
    # Convert timestamps to time objects
    if isinstance(start_time, str):
        from datetime import datetime
        start_time = datetime.fromisoformat(start_time)
    if isinstance(last_updated, str):
        from datetime import datetime
        last_updated = datetime.fromisoformat(last_updated)
    
    # Calculate elapsed time in seconds
    elapsed_seconds = (last_updated - start_time).total_seconds()
    
    # Calculate processing rate (files per second)
    if elapsed_seconds > 0:
        rate = processed_files / elapsed_seconds
    else:
        rate = 0
    
    # Estimate remaining time
    if rate > 0:
        estimated_seconds = remaining_files / rate
        estimated_minutes = estimated_seconds / 60
        estimated_hours = estimated_minutes / 60
    else:
        estimated_seconds = float('inf')
        estimated_minutes = float('inf')
        estimated_hours = float('inf')
    
    # Format estimated time
    if estimated_hours > 24:
        estimated_time = f"{estimated_hours/24:.1f} days"
    elif estimated_hours > 1:
        estimated_time = f"{estimated_hours:.1f} hours"
    elif estimated_minutes > 1:
        estimated_time = f"{estimated_minutes:.1f} minutes"
    else:
        estimated_time = f"{estimated_seconds:.1f} seconds"
    
    return {
        'status': 'running',
        'total_files': total_files,
        'processed_files': processed_files,
        'error_files': error_files,
        'remaining_files': remaining_files,
        'elapsed_time': elapsed_seconds,
        'processing_rate': rate,
        'estimated_remaining_seconds': estimated_seconds,
        'estimated_remaining_time': estimated_time,
        'percent_complete': (processed_files + error_files) / total_files * 100 if total_files > 0 else 0
    }

def interrupt_processing(
    db: PIIDatabase,
    job_id: int
) -> bool:
    """
    Mark a job as interrupted and reset processing files to pending.
    
    Args:
        db: Database connection
        job_id: Job ID to interrupt
        
    Returns:
        True if job was interrupted, False otherwise
    """
    # Get job information
    job = db.get_job(job_id)
    if not job or job.get('status') != 'running':
        return False
    
    # Reset processing files to pending
    from src.core.file_discovery import reset_stalled_files
    reset_count = reset_stalled_files(db, job_id)
    
    # Mark job as interrupted
    success = db.update_job_status(job_id, 'interrupted')
    
    logger.info(f"Job {job_id} interrupted, reset {reset_count} files to pending")
    
    return success 