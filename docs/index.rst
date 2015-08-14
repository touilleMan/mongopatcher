.. mongopatcher documentation master file, created by
   sphinx-quickstart on Fri Aug 14 09:12:15 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to mongopatcher's documentation!
========================================

.. module:: mongopatcher

.. include:: ../README.rst

.. _api:

API
---


.. automodule:: mongopatcher
   :members:


Flask-Script Extension
----------------------


For easy integration in flask projects, a flask-script manager is provided

.. code-block:: python

    from flask import Flask
    from flask.ext.script import Manager
    import pymongo
    from mongopatcher.extensions.flask import init_patcher, patcher_manager

    def init_app():
        app = Flask(__name__)
        db = pymongo.MongoClient('mongodb://localhost:27017/test')
        init_patcher(app, db.get_default_database())

    manager = Manager(init_app())
    manager.add_command("patcher", patcher_manager)
    manager.run()


.. code-block:: shell

    $ ./manage.py patcher --help
    usage: Perform incremental patch on database

    Perform incremental patch on database

    positional arguments:
      {info,upgrade,init,discover}
        info                Show version of the database
        upgrade             Apply recusively the patches available until the last
                            version
        init                Initialize mongopatcher manifest on the mongodb
                            database
        discover            List the patches available in the given patches
                            directory

    optional arguments:
      -?, --help            show this help message and exit

.. automodule:: mongopatcher.extensions.flask
   :members:


.. _GitHub: http://github.com/touilleMan/mongopatcher
