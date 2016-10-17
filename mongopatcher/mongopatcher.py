import os
import re
import pymongo
import imp
from datetime import datetime

from mongopatcher.tools import yellow, tabulate


DEFAULT_COLLECTION = 'mongopatcher'
DEFAULT_PATCHES_DIR = 'patches'


def _check_version_format(version):
    assert re.match(r"[0-9]+\.[0-9]+\.[0-9]+", version),  \
        "Invalid version number `%s` (should be x.y.z style)" % version


class DatamodelManifestError(Exception):
    pass


class Manifest:
    """
    Handle the datamodel's version and history informations
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

    def reload(self):
        self._manifest = None

    def is_initialized(self):
        """
        Check if the datamodel has a manifest registered
        """
        return bool(self.collection.find_one({'_id': 'manifest'}))

    def _load_manifest(self):
        """
        Retrieve datamodel's manifest or raise DatamodelManifestError exception
        """
        manifest = self.collection.find_one({'_id': 'manifest'})
        if not manifest:
            raise DatamodelManifestError("Datamodel's manifest is missing, "
                                         "make sure it has been initialized")
        return manifest

    def initialize(self, version, force=False):
        """
        Initialize the manifest document in the given datamodel

        :param version: Actual version of the datamodel
        :param force: Replace manifest if it already exists
        """
        _check_version_format(version)
        if not force and self.collection.find_one({'_id': 'manifest'}):
            raise DatamodelManifestError("Datamodel has already a manifest")
        manifest = self.collection.update({'_id': 'manifest'}, {
            '_id': 'manifest', 'version': version, 'history': [
                {'timestamp': datetime.utcnow(), 'version': version,
                 'reason': 'Initialize version'}
            ]}, upsert=True)
        return manifest

    def update(self, version, reason=None):
        """
        Modify the datamodel's manifest

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
    datamodel's manifest
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

    def discover(self, directory=None):
        """
        Recusively search & collect :class:`Patch`

        :param directory: Directory to search in (default: patches_dir)
        """
        directory = directory or self.patches_dir
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

    def discover_and_apply(self, directory=None, dry_run=False):
        """
        Retrieve the patches and try to apply them against the datamodel

        :param directory: Directory to search the patch in (default: patches_dir)
        :param dry_run: Don't actually apply the patches
        """
        directory = directory or self.patches_dir
        patches_dict = {p.base_version: p for p in self.discover(directory)}
        current_version = self.manifest.version
        if not patches_dict.get(current_version):
            print('No patch to apply')
            return
        if dry_run:
            msg = 'Datamodel should be in version %s !'
        else:
            msg = 'Datamodel in now in version %s !'
        pss = []
        while True:
            patch = patches_dict.get(current_version)
            if not patch:
                print(msg % current_version)
                if pss:
                    print()
                    print(yellow('\n'.join(pss)))
                return
            print('Applying patch %s => %s' % (patch.base_version,
                                               patch.target_version))
            patch_pss = [patch.ps] if patch.ps else []
            if not dry_run:
                patch_pss += self.apply_patch(patch)
            if patch_pss:
                pss.append("Patch %s:\n%s" % (patch.target_version,
                                              tabulate('\n'.join(patch_pss))))
            self.manifest.reload()
            current_version = patch.target_version

    def apply_patch(self, patch):
        """
        :return: the list of post-scriptum returned by the fixes
        """
        return patch.apply(self.manifest, self.db)


class Patch:
    """
    A patch is a list of fixes to apply against a given version of
    the datamodel

    Here is the patch apply routine:
     - check if the patch can be applied against the current datamodel
       according to it manifest
     - apply each patch's fix
     - update datamodel's manifest

    .. note::
        Make sure no other process (i.g. backend, worker) are running
        before applying the patch to prevent inconsistent states
    """

    def __repr__(self):
        return "<datamodel Patch (%s -> %s)>" % (self.base_version, self.target_version)

    def __init__(self, base_version, target_version, patchnote=None, ps=None):
        """
        :param base_version: Datamodel version to patch against
        :param target_version: Datamodel version once the patch is applied
        :param patchnote: Informations about the patch
        :param ps: Message to display after the patch has been applied
            (can be use to notify a side effect or the need
            of a manual operation - like another database rebuild - in order
            to finish the migration)

        .. note::
            If more than one patch has to be applied (i.g. updating from
            1.0.0 to 1.0.2 through 1.0.1), the ps notes will be collected
            and displayed at the very end of the patch process
        """
        _check_version_format(base_version)
        _check_version_format(target_version)

        self.base_version = base_version
        self.target_version = target_version
        self.patchnote = patchnote
        self.ps = ps
        self.fixes = []

    def can_be_applied(self, manifest, db):
        """
        Check the current datamodel state fulfill the requirements
        to run this patch
        """
        if manifest.version != self.base_version:
            raise DatamodelManifestError(
                "Datamodel's manifest shows incompatible version to "
                "apply the patch (required: %s, available: %s)" %
                (self.base_version, manifest.version))

    def apply(self, manifest, db, force=False):
        """
        Run the given patch to update the datamodel

        :return: the list of post-scriptum returned by the fixes
        """
        fixes_pss = []
        if not force:
            self.can_be_applied(manifest, db)
        for fix in self.fixes:
            print('\t%s...' % fix.__name__, flush=True, end='')
            ps = fix(db)
            if ps:
                fixes_pss.append("%s: %s" % (fix.__name__, ps))
            print(' Done !')
        manifest.update(self.target_version,
                        reason='Upgrade from %s' % self.base_version)
        return fixes_pss

    def fix(self, fn):
        """
        Decorator to register a command to run when applying the patch

        A fix must be a function that take a :class:`pymongo.MongoClient`
        instance as parameter

        .. example:

            p = Patch('0.1.0', '0.1.1', 'my_patchnote')
            @p.fix
            def my_fix(db):
                db['my_collection'].update({}, {'$set': {'updated': True}})
                return "optional post-scriptum"

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
