"""
Management Dashboard App Component

A web server that exposes endpoints for:
- Listing all activated components
- Enabling/disabling plugins
- Showing overall application state
- Real-time updates via WebSocket with component state monitoring
- Real-time log streaming with filtering
"""
from .dashboard import ManagementDashboardApp, DashboardConfig

__metadata__ = {
    "name": "Management Dashboard",
    "version": "1.3.0",
    "description": "Management Dashboard App Component",
    "wirings": ("dashboard",),
    "config": DashboardConfig
}


management_dashboard_app = ManagementDashboardApp()
initialize = management_dashboard_app.initialize
shutdown = management_dashboard_app.shutdown
wait = management_dashboard_app.wait
