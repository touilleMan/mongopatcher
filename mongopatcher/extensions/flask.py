#! /usr/bin/env python3

from flask import current_app
from flask.ext.script import Manager, prompt_bool

from mongopatcher import MongoPatcher
from mongopatcher.tools import green, tabulate


def init_patcher(app, db):
    """
    Init mongopatcher for the application

    :param app: :class:`flask.Flask` app to initialize
    :param db: :class:`pymongo.MongoClient` to work on

    .. note: This function must be called before using ``patcher_manager``
    """
    app.config.setdefault('MONGOPATCHER_PATCHES_DIR', 'patches')
    app.config.setdefault('MONGOPATCHER_COLLECTION', 'mongopatcher')
    if not hasattr(app, 'extensions'):
        app.extensions = {}
    if 'mongopatcher' not in app.extensions:
        mp = MongoPatcher(db=db,
                          patches_dir=app.config['MONGOPATCHER_PATCHES_DIR'],
                          collection=app.config['MONGOPATCHER_COLLECTION'])
        app.extensions['mongopatcher'] = mp
    else:
        # Raise an exception if extension already initialized as
        # potentially new configuration would not be loaded.
        raise Exception('Extension already initialized')
    if 'MONGOPATCHER_DATAMODEL_VERSION' not in app.config:
        # Find last version from patches
        patches = mp.discover(app.config['MONGOPATCHER_PATCHES_DIR'])
        last_version = patches[-1].target_version if patches else '1.0.0'
        app.config.setdefault('MONGOPATCHER_DATAMODEL_VERSION', last_version)
    mp.__class__.need_upgrade = need_upgrade
    mp.app_datamodel_version = app.config['MONGOPATCHER_DATAMODEL_VERSION']
    return mp


patcher_manager = Manager(usage="Perform incremental patch on database")


def need_upgrade(mp):
    """
    Check if the database's datamodel version is up to date with the
    application declared datamodel version

    :return: True if datamodel difers, False otherwise
    """
    return (not mp.manifest.version ==
            mp.app_datamodel_version)


def _get_mongopatcher():
    extensions = getattr(current_app, 'extensions') or {}
    mongopatcher = extensions.get('mongopatcher')
    if not mongopatcher:
        raise Exception('Extension mongopatcher is not initialized')
    return mongopatcher


@patcher_manager.option('-y', '--yes', action='store_true', default=False,
                        help="Don't ask for confirmation")
@patcher_manager.option('-d', '--dry_run', action='store_true', default=False,
                        help="Pretend to do the upgrades")
@patcher_manager.option('-p', '--patches', default=None,
                        help="Directory where to find the patches")
def upgrade(yes, dry_run, patches):
    """
    Upgrade the datamodel by applying recusively the patches available
    """
    patcher = _get_mongopatcher()
    if dry_run:
        patcher.discover_and_apply(directory=patches, dry_run=dry_run)
    else:
        if (yes or prompt_bool("Are you sure you want to alter %s" %
                               green(patcher.db))):
            patcher.discover_and_apply(patches)
        else:
            raise SystemExit('You changed your mind, exiting...')


@patcher_manager.option('-p', '--patches', default=None,
                        help="Directory where to find the patches")
@patcher_manager.option('-v', '--verbose', action='store_true', default=False,
                        help="Show patches' descriptions")
@patcher_manager.option('-n', '--name', default=None,
                        help="Filter the patches (can be a regex)")
def discover(patches, verbose, name):
    """List the patches available in the given patches directory"""
    patches = _get_mongopatcher().discover(directory=patches)
    if name:
        import re
        patches = [p for p in patches if re.match(name, p.target_version)]
    if not patches:
        print('No patches found')
    else:
        print('Patches available:')
        for patch in patches:
            if verbose:
                print()
                print(patch.target_version)
                print("~" * len(patch.target_version))
                print(tabulate(patch.patchnote))
            else:
                print(' - %s' % patch.target_version)


@patcher_manager.option('-f', '--force', action='store_true', default=False,
                        help="Overwrite if a manifest is already installed")
@patcher_manager.option('-v', '--version', default=None,
                        help="Specify the datamodel's version")
def init(version, force):
    """Initialize mongopatcher on the database by setting it manifest"""
    version = version or current_app.config['MONGOPATCHER_DATAMODEL_VERSION']
    _get_mongopatcher().manifest.initialize(version, force)
    print('Datamodel initialized to version %s' % version)


@patcher_manager.option('-v', '--verbose', action='store_true',
                        default=False, help="Show history")
def info(verbose):
    """Show version of the datamodel"""
    if _get_mongopatcher().manifest.is_initialized():
        print('Datamodel version: %s' % _get_mongopatcher().manifest.version)
        if verbose:
            print('\nUpdate history:')
            for update in reversed(_get_mongopatcher().manifest.history):
                reason = update.get('reason')
                reason = '(%s)' % reason if reason else ''
                print(' - %s: %s %s' % (update['timestamp'], update['version'],
                                        reason))
    else:
        print('Datamodel is not initialized')


if __name__ == "__main__":
    from flask import Flask
    import pymongo
    app = Flask(__name__)
    db = pymongo.MongoClient('mongodb://localhost:27017/test')
    init_patcher(app, db.get_default_database())
    patcher_manager.app = app
    patcher_manager.run()
