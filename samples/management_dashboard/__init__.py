"""
Management Dashboard App Component

A web server that exposes endpoints for:
- Listing all activated components
- Enabling/disabling plugins
- Showing overall application state
- Real-time updates via WebSocket with component state monitoring
- Real-time log streaming with filtering
"""
from .dashboard import ManagementDashboardApp

__all__ = ["ManagementDashboardApp"]
