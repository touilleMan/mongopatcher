import os
import re
import pymongo
import imp
from datetime import datetime


DEFAULT_COLLECTION = 'mongopatcher'
DEFAULT_PATCHES_DIR = 'patches'


def _check_version_format(version):
    assert re.match(r"[0-9]+\.[0-9]+\.[0-9]+", version),  \
        "Invalid version number `%s` (should be x.y.z style)" % version


class DatabaseManifestError(Exception):
    pass


class Manifest:
    """
    Handle the database's version and history informations
    """

    def __init__(self, db, manifest_collection):
        self.db = db
        self.collection = db[manifest_collection]
        self._manifest = None

    @property
    def version(self):
        if not self._manifest:
            self._manifest = self._load_manifest()
        return self._manifest['version']

    @property
    def history(self):
        if not self._manifest:
            self._manifest = self._load_manifest()
        return self._manifest['history']

    def is_initialized(self):
        """
        Check if the database has a manifest registered
        """
        return bool(self.collection.find_one({'_id': 'manifest'}))

    def _load_manifest(self):
        """
        Retrieve database's manifest or raise DatabaseManifestError exception
        """
        manifest = self.collection.find_one({'_id': 'manifest'})
        if not manifest:
            raise DatabaseManifestError("Database's manifest is missing, make "
                                        "sure the database is initialized")
        return manifest

    def initialize(self, version, force=False):
        """
        Initialize the manifest document in the given database

        :param version: Version to set the database
        :param force: Replace manifest if it already exists
        """
        _check_version_format(version)
        if not force and self.collection.find_one({'_id': 'manifest'}):
            raise DatabaseManifestError("Database has already a manifest")
        manifest = self.collection.update({'_id': 'manifest'}, {
            '_id': 'manifest', 'version': version, 'history': [
                {'timestamp': datetime.utcnow(), 'version': version,
                 'reason': 'Initialize version'}
            ]}, upsert=True)
        return manifest

    def update(self, version, reason=None):
        """
        Modify the database's manifest

        :param version: New version of the manifest
        :param reason: Optional reason of the update (i.g. "Update from x.y.z")
        """
        _check_version_format(version)
        return self.collection.update({'_id': 'manifest'}, {
            '$set': {'version': version},
            '$push': {'history': {
                'timestamp': datetime.utcnow(), 'version': version,
                'reason': reason}}
        })


class MongoPatcher:
    """
    Patch manager: retrieve the patches, apply them and update the
    database manifest
    """

    def __init__(self, db, patches_dir=DEFAULT_PATCHES_DIR,
                 collection=DEFAULT_COLLECTION):
        """
        :param db: :class:`pymongo.MongoClient` to work on
        :param collection: name of the collection were to store mongopatcher
        data
        """
        self.db = db
        self.patches_dir = patches_dir
        self.manifest = Manifest(db, collection)

    def discover(self, directory):
        """
        Recusively search & collect :class:`Patch`

        :param directory: Directory to search in
        """
        patches = []
        for root, dirs, files in os.walk(directory):
            for f in files:
                if not f.endswith('.py'):
                    continue
                name = f.rsplit('.', 1)[0]
                module = imp.load_source(name, '%s/%s' % (root, f))
                for elem in dir(module):
                    elem = getattr(module, elem)
                    if isinstance(elem, Patch):
                        patches.append(elem)
        return sorted(patches, key=lambda x: x.target_version)

    def discover_and_apply(self, directory, dry_run=False):
        """
        Retrieve the patches and try to apply them against the database

        :param directory: Directory to search the patch in
        :param dry_run: Don't actually apply the patches
        """
        patches_dict = {p.base_version: p for p in self.discover(directory)}
        current_version = self.manifest.version
        if not patches_dict.get(current_version):
            print('No patch to apply')
            return
        if dry_run:
            msg = 'Database should be in version %s !'
        else:
            msg = 'Database in now in version %s !'
        while True:
            patch = patches_dict.get(current_version)
            if not patch:
                print(msg % current_version)
                return
            print('Applying patch %s => %s' % (patch.base_version,
                                               patch.target_version))
            if not dry_run:
                self.apply_patch(patch)
            current_version = patch.target_version

    def apply_patch(self, patch):
        patch.apply(self.manifest, self.db)


class Patch:
    """
    A patch is a list of fixes to apply against a given version of the database

    Here is the patch apply routine:
     - check if the patch can be applied against the current database
     - apply each patch's fix
     - update database manifest

    .. note::
        Make sure no other process (i.g. backend, worker) are running
        before applying the patch to prevent inconsistent states
    """

    def __init__(self, base_version, target_version, patchnote=None):
        _check_version_format(base_version)
        _check_version_format(target_version)

        self.base_version = base_version
        self.target_version = target_version
        self.patchnote = patchnote
        self.fixes = []

    def can_be_applied(self, manifest, db):
        """
        Check the current database state fulfill the requirements
        to run this patch
        """
        if manifest.version != self.base_version:
            raise DatabaseManifestError(
                "Database's manifest shows incompatible version to "
                "apply the patch (required: %s, available: %s)" %
                (self.base_version, manifest.version))

    def apply(self, manifest, db, force=False):
        """
        Run the given patch to update the database
        """
        if not force:
            self.can_be_applied(manifest, db)
        for fix in self.fixes:
            print('\t%s...' % fix.__name__, flush=True, end='')
            fix(db)
            print(' Done !')
        manifest.update(self.target_version,
                        reason='Update from %s' % self.base_version)

    def fix(self, fn):
        """
        Decorator to register a command to run when applying the patch

        A fix must be a function that take a :class:`pymongo.MongoClient`
        instance as parameter

        .. example:

            p = Patch('0.1.0', '0.1.1')
            @p.fix
            def my_fix(db):
                db['my_collection'].update({}, {'$set': {'updated': True}})

        .. note:
            Fix order is not guarantee. If you need it, consider using sub
            functions ::

                @p.fix
                def macro_fix(db):
                    first_fix_to_apply(db)
                    second_fix_to_apply(db)
        """
        self.fixes.append(fn)
        return fn
