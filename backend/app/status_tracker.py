"""Status tracking for system monitoring and activity logging."""
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
from collections import deque
import logging

logger = logging.getLogger(__name__)


class SystemStatus(Enum):
    """System status enumeration."""
    RUNNING = "Running"
    STOPPED = "Stopped"


class AutomationStatus(Enum):
    """Automation status enumeration."""
    IDLE = "Idle"
    PROCESSING = "Processing"
    ERROR = "Error"


class LoginStatus(Enum):
    """Login status enumeration."""
    LOGGED_IN = "Logged in"
    NOT_LOGGED_IN = "Not logged in"


class SessionStatus(Enum):
    """Session status enumeration."""
    ACTIVE = "Active"
    EXPIRED = "Expired"


class StatusTracker:
    """Tracks system status, login status, current tasks, and activity logs."""
    
    def __init__(self, max_activity_logs: int = 100):
        """
        Initialize status tracker.
        
        Args:
            max_activity_logs: Maximum number of activity logs to keep in memory
        """
        # System status
        self.backend_status = SystemStatus.RUNNING
        self.automation_status = AutomationStatus.IDLE
        self.last_activity_time: Optional[datetime] = None
        
        # Login/Session status
        self.login_status = LoginStatus.NOT_LOGGED_IN
        self.session_status = SessionStatus.EXPIRED
        self.last_login_time: Optional[datetime] = None
        self.session_valid_until: Optional[datetime] = None
        
        # Current task
        self.current_task: Optional[str] = None
        self.current_task_started_at: Optional[datetime] = None
        self.current_task_details: Optional[Dict] = None
        
        # Activity log (most recent first)
        self.activity_logs: deque = deque(maxlen=max_activity_logs)
        
        # Result summary
        self.last_check_time: Optional[datetime] = None
        self.last_availability_result: Optional[Dict] = None
        self.last_reservation_result: Optional[Dict] = None
        
        # Errors/Warnings
        self.recent_errors: deque = deque(maxlen=20)
        self.recent_warnings: deque = deque(maxlen=20)
    
    def set_backend_status(self, status: SystemStatus):
        """Set backend status."""
        self.backend_status = status
        self._add_activity_log("system", f"Backend status changed to: {status.value}", {"status": status.value})
    
    def set_automation_status(self, status: AutomationStatus, details: Optional[str] = None):
        """Set automation status."""
        self.automation_status = status
        self.last_activity_time = datetime.utcnow()
        self._add_activity_log("automation", f"Automation status: {status.value}" + (f" - {details}" if details else ""), {"status": status.value, "details": details})
    
    def set_login_status(self, status: LoginStatus, session_valid_until: Optional[datetime] = None):
        """Set login status."""
        self.login_status = status
        if status == LoginStatus.LOGGED_IN:
            self.last_login_time = datetime.utcnow()
            self.session_status = SessionStatus.ACTIVE
            self.session_valid_until = session_valid_until
            self._add_activity_log("login", "Successfully logged in", {"login_time": self.last_login_time.isoformat()})
        else:
            self.session_status = SessionStatus.EXPIRED
            self.session_valid_until = None
            self._add_activity_log("login", "Logged out or session expired", {})
    
    def set_current_task(self, task: Optional[str], details: Optional[Dict] = None):
        """Set current task being performed."""
        if task:
            self.current_task = task
            self.current_task_started_at = datetime.utcnow()
            self.current_task_details = details or {}
            self.automation_status = AutomationStatus.PROCESSING
            self._add_activity_log("task", f"Started: {task}", details or {})
        else:
            # Task completed
            if self.current_task:
                duration = (datetime.utcnow() - self.current_task_started_at).total_seconds() if self.current_task_started_at else 0
                self._add_activity_log("task", f"Completed: {self.current_task} (took {duration:.1f}s)", self.current_task_details or {})
            self.current_task = None
            self.current_task_started_at = None
            self.current_task_details = None
            self.automation_status = AutomationStatus.IDLE
    
    def add_activity_log(self, category: str, message: str, data: Optional[Dict] = None, level: str = "info"):
        """
        Add activity log entry.
        
        Args:
            category: Category of activity (e.g., "navigation", "login", "availability", "reservation")
            message: Human-readable message
            data: Additional data (optional)
            level: Log level (info, warning, error)
        """
        self._add_activity_log(category, message, data, level)
    
    def touch_activity_time(self):
        """Update last_activity_time to indicate system is still active without adding a log entry."""
        self.last_activity_time = datetime.utcnow()
    
    def _add_activity_log(self, category: str, message: str, data: Optional[Dict] = None, level: str = "info"):
        """Internal method to add activity log."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "category": category,
            "message": message,
            "data": data or {},
            "level": level
        }
        self.activity_logs.appendleft(log_entry)  # Add to front (most recent first)
        self.last_activity_time = datetime.utcnow()
    
    def set_availability_result(self, found: bool, slots_count: int = 0, details: Optional[Dict] = None):
        """Set last availability check result."""
        self.last_check_time = datetime.utcnow()
        self.last_availability_result = {
            "found": found,
            "slots_count": slots_count,
            "timestamp": self.last_check_time.isoformat(),
            "details": details or {}
        }
        self._add_activity_log(
            "availability",
            f"Availability check: {'Found' if found else 'Not found'} ({slots_count} slots)" if found else "Availability check: Not found",
            self.last_availability_result
        )
    
    def set_reservation_result(self, success: bool, reservation_number: Optional[str] = None, error: Optional[str] = None, details: Optional[Dict] = None):
        """Set last reservation attempt result."""
        self.last_reservation_result = {
            "success": success,
            "reservation_number": reservation_number,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {}
        }
        if success:
            self._add_activity_log("reservation", f"Reservation successful: {reservation_number}", self.last_reservation_result)
        else:
            self._add_activity_log("reservation", f"Reservation failed: {error}", self.last_reservation_result, "error")
    
    def add_error(self, message: str, details: Optional[Dict] = None):
        """Add error message."""
        error_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "message": message,
            "details": details or {}
        }
        self.recent_errors.appendleft(error_entry)
        self.automation_status = AutomationStatus.ERROR
        self._add_activity_log("error", message, details, "error")
    
    def add_warning(self, message: str, details: Optional[Dict] = None):
        """Add warning message."""
        warning_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "message": message,
            "details": details or {}
        }
        self.recent_warnings.appendleft(warning_entry)
        self._add_activity_log("warning", message, details, "warning")
    
    def get_status(self) -> Dict:
        """Get comprehensive system status."""
        # Check if session is expired
        if self.session_valid_until and datetime.utcnow() > self.session_valid_until:
            self.session_status = SessionStatus.EXPIRED
            if self.login_status == LoginStatus.LOGGED_IN:
                self.login_status = LoginStatus.NOT_LOGGED_IN
        
        return {
            # 1. System status
            "system": {
                "backend_status": self.backend_status.value,
                "automation_status": self.automation_status.value,
                "last_activity_time": self.last_activity_time.isoformat() if self.last_activity_time else None
            },
            # 2. Login/Session status
            "login": {
                "login_status": self.login_status.value,
                "session_status": self.session_status.value,
                "last_login_time": self.last_login_time.isoformat() if self.last_login_time else None,
                "session_valid_until": self.session_valid_until.isoformat() if self.session_valid_until else None
            },
            # 3. Current task
            "current_task": {
                "task": self.current_task,
                "started_at": self.current_task_started_at.isoformat() if self.current_task_started_at else None,
                "details": self.current_task_details or {}
            },
            # 4. Activity log
            "activity_log": list(self.activity_logs),  # Convert deque to list
            # 5. Result summary
            "results": {
                "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
                "last_availability_result": self.last_availability_result,
                "last_reservation_result": self.last_reservation_result
            },
            # 6. Errors/Warnings
            "errors": {
                "recent_errors": list(self.recent_errors),
                "recent_warnings": list(self.recent_warnings)
            }
        }


# Global status tracker instance
status_tracker = StatusTracker()

