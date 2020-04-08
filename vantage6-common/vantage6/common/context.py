import os
import sys
import appdirs

import logging
import vantage6.common.colorer

from pathlib import Path

from vantage6.common import Singleton
from vantage6.common.globals import DEFAULT_ENVIRONMENT, APPNAME, PACAKAGE_FOLDER
from vantage6.common.configuration_manager import ConfigurationManager

class AppContext(metaclass=Singleton):

    # FIXME: drop the prefix "INST_": a *class* is assigned.
    # FIXME: this does not need to be a class attribute, but ~~can~~_should_
    #        be set in __init__
    #        I think the same applies to LOGGING_ENABLED
    INST_CONFIG_MANAGER = ConfigurationManager
    LOGGING_ENABLED = True

    def __init__(self, instance_type, instance_name, environment=DEFAULT_ENVIRONMENT,
        system_folders=False, config_file=None):
        """
        Create a new AppContext instance.

        Args:
            instance_type (str): 'server' or 'node'
            instance_name (str): name of the configuration
            system_folders (bool): use system folders instead of user folders
            environment (str): Environment within the config file to use. Can
                be any of 'application', 'dev', 'test', 'acc' or 'prod'.
            config_file (str): Path to a specific config file. If left as None,
                OS specific folder will be used to find the configuration file
                specified by `instance_name`.
        """

        # lookup system / user directories
        self.name = instance_name
        self.scope = "system" if system_folders else "user"
        self.set_folders(instance_type, instance_name, system_folders)

        # configuration environment, load a single configuration from
        # entire confiration file (which can contain multiple environments)
        # self.config_file = self.config_dir / f"{instance_name}.yaml"

        # if config_file is None:
        #     config_file = f"{instance_name}.yaml"
        self.config_file = self.find_config_file(
            instance_type,
            instance_name,
            config_file
        )

        # will load a specific environment in the config_file, this
        # triggers to set the logging as this is env dependant
        self.environment = environment

        # Log some history
        # FIXME: this should probably be moved to the actual app
        module_name = __name__.split('.')[-1]
        self.log = logging.getLogger(module_name)
        self.log.info("#" * 80)
        self.log.info(f'#{APPNAME:^78}#')
        self.log.info("#" * 80)
        self.log.info(f"Started application {APPNAME} with environment {self.environment}")
        self.log.info("Current working directory is '%s'" % os.getcwd())
        self.log.info("Succesfully loaded configuration from '%s'" % self.config_file)
        self.log.info("Logging to '%s'" % self.log_file)

    @classmethod
    def from_external_config_file(cls, path, instance_type,
        environment=DEFAULT_ENVIRONMENT, system_folders=False):
        instance_name = Path(path).stem

        self_ = cls.__new__(cls)
        self_.set_folders(instance_type, instance_name, system_folders)
        self_.config_dir = Path(path).parent
        self_.config_file = path
        self_.environment = environment
        return self_

    @classmethod
    def config_exists(cls, instance_type, instance_name, environment=DEFAULT_ENVIRONMENT,
        system_folders=False):

        try:
            config_file = cls.find_config_file(
                instance_type,
                instance_name,
                system_folders,
                verbose=False
            )

        except Exception as e:
            return False

        """
        # obtain location of config file
        d = appdirs.AppDirs(APPNAME, "")
        config_dir = d.site_config_dir if system_folders else d.user_config_dir
        config_file = Path(config_dir) / instance_type / (instance_name+".yaml")

        if not Path(config_file).exists():
            return False
        """

        # check that environment is present in config-file
        config_manager = cls.INST_CONFIG_MANAGER.from_file(config_file)
        return bool(getattr(config_manager, environment))

    @staticmethod
    def instance_folders(instance_type, instance_name, system_folders):
        """Return OS specific folders for storing logs, data and config files"""
        d = appdirs.AppDirs(APPNAME, "")

        if system_folders:
            return {
                "log": Path(d.site_data_dir) / instance_type,
                "data": Path(d.site_data_dir) / instance_type / instance_name,
                "config": Path(d.site_config_dir) / instance_type
            }
        else:
            return {
                "log": Path(d.user_log_dir) / instance_type,
                "data": Path(d.user_data_dir) / instance_type / instance_name,
                "config": Path(d.user_config_dir) / instance_type
            }

    @classmethod
    def available_configurations(cls, instance_type, system_folders):
        """Returns a list of configuration managers."""
        folders =  cls.instance_folders(instance_type, "", system_folders)

        # potential configuration files
        config_files = Path(folders["config"]).glob("*.yaml")

        configs = []
        failed = []
        for file_ in config_files:
            try:
                conf_manager = cls.INST_CONFIG_MANAGER.from_file(file_)
                if conf_manager.is_empty:
                    failed.append(file_)
                else:
                    configs.append(conf_manager)
            except Exception:
                failed.append(file_)

        return configs, failed

    @property
    def log_file(self):
        assert self.config_manager, \
            "Log file unkown as configuration manager not initialized"

        if self.config.get("logging"):
            if self.config.get("logging").get("file"):
                return self.log_dir / self.config.get("logging").get("file")
        file_ = f"{self.config_manager.name}-{self.environment}-{self.scope}.log"
        return self.log_dir / file_

    @property
    def config_file_name(self):
        return self.__config_file.stem

    @property
    def config_file(self):
        return self.__config_file

    @config_file.setter
    def config_file(self, path):
        assert Path(path).exists(), f"config {path} not found"
        self.__config_file = Path(path)
        self.config_manager = self.INST_CONFIG_MANAGER.from_file(path)

    @property
    def environment(self):
        return self.__environment

    @environment.setter
    def environment(self, env):
        assert self.config_manager, \
            "Environment set before ConfigurationManager is initialized..."
        assert env in self.config_manager.available_environments, \
            f"Requested environment {env} is not found in the configuration"
        self.__environment = env
        self.config = self.config_manager.get(env)
        if self.LOGGING_ENABLED:
            self.setup_logging()

    @classmethod
    def find_config_file(cls, instance_type, instance_name, system_folders,
        config_file=None, verbose=True):
        """Find a configuration file."""
        if config_file is None:
            config_file = f"{instance_name}.yaml"

        config_dir = cls.instance_folders(
            instance_type,
            instance_name,
            system_folders
        ).get('config')

        dirs = [
            config_dir,
            './',
        ]

        for location in dirs:
            # If config_file is an absolute path `os.path.join()` ignores
            # `location`.
            fullpath = os.path.join(location, config_file)

            if os.path.exists(fullpath):
                return fullpath

        if verbose:
            msg = f'Could not find configuration file "{config_file}"!?'
            print(msg)
            print('Tried the following directories:')
            for d in dirs:
                print(f' * {d}')

        raise Exception(msg)

    def get_data_file(self, filename):
        """Return the path to a data file."""
        # If filename is an absolute path `os.path.join()` ignores
        # `self.data_dir`.
        if not filename:
            raise Exception('Argument "filename" should be provided!')
        return os.path.join(self.data_dir, filename)

    def set_folders(self, instance_type, instance_name, system_folders):
        dirs = self.instance_folders(
            instance_type,
            instance_name,
            system_folders
        )

        self.log_dir = dirs.get("log")
        self.data_dir = dirs.get("data")
        self.config_dir = dirs.get("config")

    def setup_logging(self):
        """Setup a basic logging mechanism."""
        log_config = self.config["logging"]

        level = getattr(logging, log_config["level"].upper())
        format_ = log_config["format"]
        datefmt = log_config.get("datefmt", "")

        # make sure the log-file exists
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

        # Create the root logger
        logger = logging.getLogger()
        logger.setLevel(level)

        # Create RotatingFileHandler
        rfh = logging.handlers.RotatingFileHandler(
            self.log_file,
            maxBytes=1024*log_config["max_size"],
            backupCount=log_config["backup_count"]
        )
        rfh.setLevel(level)
        rfh.setFormatter(logging.Formatter(format_, datefmt))
        logger.addHandler(rfh)

        # Check what to do with the console output ...
        if log_config["use_console"]:
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(level)
            ch.setFormatter(logging.Formatter(format_, datefmt))
            logger.addHandler(ch)

        # Finally, capture all warnings using the logging mechanism.
        logging.captureWarnings(True)
