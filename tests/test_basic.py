import pytest
from os import path

from pymongo import MongoClient
from mongopatcher import MongoPatcher
from mongopatcher.mongopatcher import DatamodelManifestError


PATCHES_DIR = path.abspath(path.dirname(__file__)) + '/test_patches'
TEST_DB = 'test'

conn = MongoClient()
db = conn[TEST_DB]


def get_manifest():
    return db.mongopatcher.find_one({'_id': 'manifest'})


def update_manifest(update):
    return db.mongopatcher.update_one({'_id': 'manifest'}, update)


class TestBasic:

    def setup_method(cls):
        conn.drop_database(TEST_DB)
        cls.patcher = MongoPatcher(db, patches_dir=PATCHES_DIR)

    def test_discover(self):
        patches = self.patcher.discover()
        assert len(patches) == 4

    def test_discover_and_apply(self):
        self.patcher.manifest.initialize('0.0.0')
        self.patcher.discover_and_apply()
        assert get_manifest()['version'] == '1.1.0'
        assert self.patcher.manifest.version == '1.1.0'
        assert len(self.patcher.manifest.history) == 5

    def test_initialize(self):
        assert not get_manifest()
        self.patcher.manifest.initialize('0.0.1')
        manifest = get_manifest()
        assert manifest
        assert manifest['version'] == '0.0.1'

    def test_reload_manifest(self):
        self.patcher.manifest.initialize('0.0.1')
        update_manifest({'$set': {'version': '0.0.x'}})
        self.patcher.manifest.reload()
        assert self.patcher.manifest.version == '0.0.x'

    def test_no_manifest(self):
        assert not self.patcher.manifest.is_initialized()
        with pytest.raises(DatamodelManifestError):
            self.patcher.manifest.version
        self.patcher.manifest.initialize('0.0.1')
        assert self.patcher.manifest.is_initialized()
        assert self.patcher.manifest.version == '0.0.1'
