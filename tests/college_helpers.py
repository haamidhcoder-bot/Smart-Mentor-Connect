"""Test helpers: every college has its own database, so tests register a
college and make app contexts use it."""
from flask.ctx import AppContext

from shared import colleges


def register_college(app, name="Test College"):
    """Create a college (own throw-away database) and make every app context
    of ``app`` use it, so tests can keep writing ``with app.app_context(): ...``.
    The slug is stored as ``app.test_college``."""
    info = colleges.create_college(name)
    app.test_college = info.slug

    class CollegeAppContext(AppContext):
        def push(self):
            super().push()
            colleges.activate(info.slug)

    app.app_context = lambda: CollegeAppContext(app)
    return info


def log_in_session(client, **session_values):
    """Mark the test client as logged in to the app's test college."""
    with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["college"] = client.application.test_college
        sess["username"] = "tester@example.com"
        sess.update(session_values)


def load_side(side, root):
    """Import one side's ``app`` package under a unique name and build it."""
    import importlib.util
    import os
    import sys

    pkg = os.path.join(root, f"{side}_side", "app")
    name = f"{side}_multi_college_app"
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(pkg, "__init__.py"), submodule_search_locations=[pkg])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.create_app()
