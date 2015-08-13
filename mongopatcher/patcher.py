import re
import pymongo
from os import environ


PATCHES_DICT = {}
DEFAULT_COLLECTION = 'mongopatcher'
DEFAULT_PATCHES_DIR = 'patches'


def _check_version_format(version):
    assert re.match(r"[0-9]+\.[0-9]+\.[0-9]+", version),  \
        "Invalid version number `%s` (should be x.y.z style)" % version


class DatabaseManifestError(Exception):
    pass


class Manifest:

    def __init__(self, db, manifest_collection):
        self.db = db
        self.collection = db[manifest_collection]
        self._manifest = None

    @property
    def version(self):
        if not self._manifest:
            self._manifest = self._load_manifest()
        return self._manifest['version']

    def is_initialized(self):
        return bool(collection.find_one({'_id': 'manifest'}))

    def _load_manifest(self):
        """
        Retrieve database's manifest or raise DatabaseManifestError exception
        """
        manifest = collection.find_one({'_id': 'manifest'})
        if not manifest:
            raise DatabaseManifestError("Database's manifest is missing, make "
                                        "sure the database is initialized")
        return manifest

    def initialize(version, force=False):
        """
        Initialize the manifest document in the given database

        :param version: Version to set the database
        :param force: Replace manifest if it already exists
        """
        _check_version_format(version)
        if not force and self.collection.find_one({'_id': 'manifest'}):
            raise DatabaseManifestError("Database has already a manifest")
        manifest = self.collection.update(
            {'_id': 'manifest', 'version': version}, upsert=True)
        return manifest

    def update(self, version):
        """
        Modify the database's manifest
        """
        _check_version_format(version)
        return collection.update({'_id': 'manifest'},
                                 {'$set': {'version': version}})


class MongoPatcher:

    def __init__(self, db, patches_dir=DEFAULT_PATCHES_DIR,
                 collection=DEFAULT_COLLECTION):
        """
        :param db: :class:`pymongo.MongoClient` to work on
        :param collection: name of the collection were to store mongopatcher
        data
        """
        self.db = db
        self.patches_dir = patches_dir
        self.manifest = Manifest(db, collection_name)
        self.collection = db[collection]

    def init_db(version):
        _check_version_format(version)

    def init_app(self, app):
        self.app = app
        self.host = app.config['MONGODB_URL']
        self.app_version = app.config['APPLICATION_VERSION']
        _check_version_format(self.app_version)

    def discover_and_apply(dir):
        """
        Retrieve the patches for the given directory and try to apply
        them against the database
        """
        while True:
            pass

    def apply_patch(self, patch):
        patch.apply(self.manifest, self.db)


class Patch:
    """
    A patch is a list of fixes to apply against a given version of the database

    Here is the patch apply routine:
     - check if the patch can be applied against the current database
     - apply each patch's fix
     - update database manifest

    .. note:: Make sure no other process (i.g. backend, worker) are running
    before applying the patch to prevent inconsistent states
    """

    def __init__(self, base_version, target_version, patchnote=None):
        _check_version_format(base_version)
        _check_version_format(target_version)
        assert base_version not in PATCHES_DICT, "A patch has already been"  \
            " registered to updgrade version `%s`" % base_version

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
        print('Applying patch %s => %s' %
              (self.base_version, self.target_version))
        if not force:
            self.can_be_applied(manifest, db)
        for fix in self.fixes:
            print('\t%s...' % fix.__name__, flush=True, end='')
            fix(db)
            print(' Done !')
        manifest.update(self.target_version)
        print('Database in now in version %s !' % self.target_version)

    def fix(self, fn):
        """
        Decorator to register a command to run when applying the patch

        A fix must be a function that take a :class:`pymongo.MongoClient`
        instance as parameter

        :example:

            p = Patch('0.1.0', '0.1.1')
            @p.fix
            def my_fix(db):
                db['my_collection'].update({}, {'$set': {'updated': True}})
        """
        self.fixes.append(fn)
        return fn
