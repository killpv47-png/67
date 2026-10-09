from . import onboarding, menu, repos, newrepo, upload, secrets, actions, settings_h, help_h, ai_chat  # noqa: F401

ROUTERS = [
    onboarding.router, menu.router, repos.router, newrepo.router, upload.router, secrets.router,
    actions.router, settings_h.router, help_h.router, ai_chat.router,
]
