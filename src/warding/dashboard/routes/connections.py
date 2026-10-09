"""Route registration for terminal, projects, channels, auth tokens, instances, cloud.

One contiguous slice of the dashboard's route table, kept in its original
order. aiohttp resolves routes in REGISTRATION order, and several routes here
rely on a literal path being registered before a pattern that would otherwise
swallow it, so neither the lines within this function nor the order in which
``server.start_dashboard`` calls the registrars may be rearranged.
"""

from __future__ import annotations

from aiohttp import web

from warding.dashboard import (
    handlers,
    handlers_channel,
    handlers_cloud,
    handlers_instances,
    handlers_project,
)
from warding.dashboard.handlers.auth_mobile import api_auth_mobile_link
from warding.dashboard.handlers.auth_refresh import (
    api_auth_logout,
    api_auth_me,
    api_auth_refresh,
)


def register(app: web.Application) -> None:
    """Register the connections routes on *app*."""
    # Terminal (CLI panel)
    app.router.add_get("/api/ws/terminal/{session_id}", handlers.api_terminal_ws)
    app.router.add_post("/api/terminal/sessions", handlers.api_terminal_create)
    app.router.add_get("/api/terminal/sessions", handlers.api_terminal_list)
    app.router.add_post("/api/terminal/redact", handlers.api_terminal_redact)
    app.router.add_post("/api/terminal/complete", handlers.api_terminal_complete)
    app.router.add_delete("/api/terminal/sessions/{session_id}", handlers.api_terminal_delete)
    app.router.add_get("/api/taskrunner/refine", handlers.api_taskrunner_refine_status)
    app.router.add_post("/api/taskrunner/refine", handlers.api_taskrunner_refine)
    app.router.add_post("/api/taskrunner/refine/cancel", handlers.api_taskrunner_refine_cancel)
    app.router.add_post("/api/taskrunner/refine/answer", handlers.api_taskrunner_refine_answer)

    # Projects
    app.router.add_get("/api/projects", handlers_project.api_projects_list)
    app.router.add_get("/api/projects/{id}", handlers_project.api_project_get)
    app.router.add_post("/api/projects", handlers_project.api_project_create)
    app.router.add_put("/api/projects/{id}", handlers_project.api_project_update)
    app.router.add_delete("/api/projects/{id}", handlers_project.api_project_delete)
    app.router.add_get("/api/activities", handlers_project.api_activities_list)
    app.router.add_post("/api/comments", handlers_project.api_comment_add)
    app.router.add_get("/api/comments", handlers_project.api_comments_list)
    app.router.add_delete("/api/comments/{id}", handlers_project.api_comment_delete)

    # Channels
    app.router.add_get("/api/channels/presets", handlers_channel.api_channel_presets)
    app.router.add_get("/api/channels", handlers_channel.api_channels_list)
    app.router.add_post("/api/channels", handlers_channel.api_channel_create)
    app.router.add_get("/api/channels/{id}", handlers_channel.api_channel_get)
    app.router.add_delete("/api/channels/{id}", handlers_channel.api_channel_close)
    app.router.add_post(
        "/api/channels/{id}/clear-context", handlers_channel.api_channel_clear_context
    )
    app.router.add_post("/api/channels/{id}/messages", handlers_channel.api_channel_post)
    app.router.add_post("/api/channels/{id}/agents", handlers_channel.api_channel_add_agent)
    app.router.add_patch(
        "/api/channels/{id}/agents/{aid}", handlers_channel.api_channel_update_agent
    )
    app.router.add_delete(
        "/api/channels/{id}/agents/{aid}", handlers_channel.api_channel_dismiss_agent
    )
    app.router.add_post(
        "/api/channels/{id}/agents/{aid}/wake", handlers_channel.api_channel_wake_agent
    )
    app.router.add_post(
        "/api/channels/{id}/agents/{aid}/approve", handlers_channel.api_channel_approve_agent
    )

    # OAuth-style refresh tokens for dashboard auth. POST /api/auth/refresh and
    # POST /api/auth/logout self-authenticate via the refresh cookie (the
    # token_auth middleware exempts them); GET /api/auth/me and POST
    # /api/auth/mobile-link are gated by the standard access-cookie auth.
    app.router.add_get("/api/auth/me", api_auth_me)
    app.router.add_post("/api/auth/mobile-link", api_auth_mobile_link)
    app.router.add_post("/api/auth/refresh", api_auth_refresh)
    app.router.add_post("/api/auth/logout", api_auth_logout)

    # Instances (multi-instance management) — owner-only, gated by instances.enabled
    app.router.add_get("/api/instances", handlers_instances.api_instances_list)
    app.router.add_get(
        "/api/instances/search-sessions", handlers_instances.api_instances_search_sessions
    )
    app.router.add_post("/api/instances", handlers_instances.api_instances_add)
    app.router.add_patch("/api/instances/{id}", handlers_instances.api_instances_update)
    app.router.add_delete("/api/instances/{id}", handlers_instances.api_instances_remove)
    app.router.add_get("/api/instances/{id}/status", handlers_instances.api_instances_status)
    app.router.add_post("/api/instances/{id}/connect", handlers_instances.api_instances_connect)
    app.router.add_post(
        "/api/instances/{id}/refresh-token", handlers_instances.api_instances_refresh_token
    )
    app.router.add_post(
        "/api/instances/{id}/disconnect", handlers_instances.api_instances_disconnect
    )
    app.router.add_post("/api/instances/{id}/restart", handlers_instances.api_instances_restart)
    app.router.add_post(
        "/api/instances/{id}/send-session", handlers_instances.api_instances_send_session
    )

    # Cloud provisioning (owner-only, user-initiated) — provision a Warding
    # instance in the user's own AWS account as a durable launch job.
    app.router.add_get("/api/cloud/preflight", handlers_cloud.api_cloud_preflight)
    app.router.add_get("/api/cloud/iam-policy", handlers_cloud.api_cloud_iam_policy)
    app.router.add_get("/api/cloud/launch", handlers_cloud.api_cloud_launch_list)
    app.router.add_post("/api/cloud/launch", handlers_cloud.api_cloud_launch_create)
    app.router.add_get("/api/cloud/launch/{id}", handlers_cloud.api_cloud_launch_get)
    app.router.add_post("/api/cloud/launch/{id}/cancel", handlers_cloud.api_cloud_launch_cancel)
    app.router.add_post("/api/cloud/launch/{id}/signin", handlers_cloud.api_cloud_launch_signin)
    app.router.add_post("/api/cloud/{tag}/stop", handlers_cloud.api_cloud_stop)
    app.router.add_post("/api/cloud/{tag}/start", handlers_cloud.api_cloud_start)
    app.router.add_delete("/api/cloud/{tag}", handlers_cloud.api_cloud_destroy)
