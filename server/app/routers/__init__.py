from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    from app.routers.v1 import health, system_info, auth, knowledge_base, sync, document, search, agent, agent_tool, api_key, conversation, conversation_step, chat, channel, upload, public, kb_permission_rule, help_center, help_center_tab, public_help_center

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(system_info.router, prefix="/api/v1")
    # Tenant CRUD API moved to closed-source extension (private/extensions/server/tenants/).
    # Open-source deployments rely on the auto-provisioned default tenant from app.db.seed.
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(knowledge_base.router, prefix="/api/v1")
    app.include_router(sync.router, prefix="/api/v1")
    app.include_router(document.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")
    app.include_router(agent_tool.router, prefix="/api/v1")
    app.include_router(api_key.router, prefix="/api/v1")
    app.include_router(conversation.router, prefix="/api/v1")
    app.include_router(conversation_step.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(channel.router, prefix="/api/v1")
    app.include_router(upload.router, prefix="/api/v1")
    app.include_router(public.router, prefix="/api/v1")
    app.include_router(kb_permission_rule.router, prefix="/api/v1")
    app.include_router(help_center.router, prefix="/api/v1")
    app.include_router(help_center_tab.router, prefix="/api/v1")
    app.include_router(public_help_center.router, prefix="/api/v1")
