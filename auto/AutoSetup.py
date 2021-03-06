#!/usr/bin/env python3

"""
Mostly automated installation for a new CMS + gitolite server.
"""

import getpass
import os
import subprocess
import sys
import requests


class Log():
    """
    An object for interacting with the user, including colored printing
    and prompts.
    """

    modifiers = {
        "normal":   "\033[0m",
        "green":    "\033[92m",
        "yellow":   "\033[93m",
        "red":      "\033[91m"
    }

    @staticmethod
    def pretty_print(text, modifier, end='\n'):
        """
        Print the given text with the given modifier (color),
        then return to normal mode.
        """
        print(modifier, text, Log.modifiers["normal"], sep="", end=end)

    @staticmethod
    def info(text, end='\n'):
        """
        Print the given text in green.
        """
        Log.pretty_print(text, Log.modifiers["green"], end=end)

    @staticmethod
    def fail(text, end='\n'):
        """
        Print the given text in red.
        """
        Log.pretty_print(text, Log.modifiers["red"], end=end)

    @staticmethod
    def warn(text, end='\n'):
        """
        Print the given text in yellow.
        """
        Log.pretty_print(text, Log.modifiers["yellow"], end=end)

    @staticmethod
    def prompt(question, options, default=None):
        """
        Prompt to choose between several options, with optional default.
        The user can input an entire option or just the first letter.
        For example: Continue? ([y]es [n]o)
        """
        options_text = " ".join("[%s]%s" % (option[0], option[1:])
                                for option in options)
        text = "%s (%s) " % (question, options_text)
        letters = {option[0]: option for option in options}
        assert len(letters) == len(options)

        while True:
            warn(text, end="")
            choice = str(input())
            if default is not None and choice == "":
                choice = default
                break
            elif choice in options:
                break
            elif choice in letters:
                choice = letters[choice]
                break
        return choice

    @staticmethod
    def prompt_dir(question, must_exist, must_not_exist, create, default=None):
        """
        Prompt to choose a directory (absolute path).
        """
        text = question
        if default is not None:
            text += " (default: %s) " % (default,)

        while True:
            warn(text, end="")
            choice = os.path.expanduser(str(input()))
            if default is not None and choice == "":
                choice = default
                break
            warn("Trying path: %s" % choice)
            exists = os.path.isdir(choice)
            if exists:
                if must_not_exist:
                    warn("Error: path already exists.")
                    continue
                else:
                    break
            else:
                if must_exist:
                    warn("Error: path doesn't exist.")
                    continue
                else:
                    if create:
                        os.makedirs(choice)
                    break

        return choice

    @staticmethod
    def prompt_password(question):
        """
        Prompt for a password, without echoing it to the terminal.
        """
        while True:
            password = getpass.getpass(question, stream=None)
            if password != "":
                break
        return password


class Runner():
    """
    An object for executing actions in the system.
    """

    interact = 2

    @staticmethod
    def set_interact(interact):
        """
        Set the interactivity level.
        """
        Runner.interact = interact

    @staticmethod
    def run_step(user_index, step, num_steps):
        """
        Run a given step (action). The step is a dictionary containing
        the fields "text" and "function", which are the description
        and function to run, respectively. The index and total number
        of steps are given for friendly printing.

        Return True if the step succeeded or was skipped,
        and the program should proceed.
        """
        info("[%d/%d: %s]" % (user_index, num_steps, step["text"]))

        if Runner.interact > 1:
            choice = prompt("Continue?", ["yes", "no", "skip"])
            if choice == "skip":
                info("[Skipping step %d]" % (user_index,))
                return True
            elif choice == "no":
                fail("[Breaking before step %d]" % (user_index,))
                return False

        function = step["function"]
        success = True
        try:
            success = function()
        except Exception as e:
            fail(e)
            success = False

        if success:
            info("[%d/%d: Done]" % (user_index, num_steps))
        else:
            fail("[Step {0} failed. Clean up manually and "
                 "run \"AutoSetup.py -s {0}\" to start from "
                 "here]".format(user_index))

        return success

    @staticmethod
    def run(commands, fail_abort=True):
        """
        Run the described commands list. If fail_abort is True,
        and the return code is not zero, raise an exception.
        The shell is given to the executed program.

        Return the same return code.
        """
        command_string = " ".join(commands)
        warn("[*** Executing: %s *** ]" % command_string)

        if Runner.interact > 2:
            choice = prompt("Continue?", ["yes", "no", "skip"])
            if choice == "skip":
                info("[Skipping this execution]")
                return 0
            elif choice == "no":
                raise Exception("User interrupt")

        return_code = subprocess.call(commands)
        if return_code != 0 and fail_abort:
            raise Exception("[Return code was %d for: %s]" %
                            (return_code, command_string))

        warn("[*** Done executing: %s *** ]" % command_string)
        return return_code

    @staticmethod
    def run_with_io(commands, input_str=None, fail_abort=True):
        """
        Run the described commands list, with the given input. If fail_abort
        is True, and the return code is not zero, raise an exception.
        The shell is not given to the executed program.

        Return a tuple containing the output and the return code.
        """
        command_string = " ".join(commands)
        process = subprocess.Popen(commands, stdout=subprocess.PIPE)
        stdout, _ = process.communicate(input=input_str)
        return_code = process.returncode

        if return_code != 0 and fail_abort:
            raise Exception("[Return code was %d for: %s]" %
                            (return_code, command_string))

        # Decode the bytes to a normal string.
        return stdout.decode(), return_code

    @staticmethod
    def write(path, text, sudo=False):
        """
        Write the given text to the given path.
        Use sudo if the flag is given.
        """

        # A temporary file is used. Makes the sudo part easier.
        temp_path = "/tmp/auto_script_tmp.txt"
        with open(temp_path, 'w') as f:
            f.write(text)
        if sudo:
            run(["sudo", "cp", temp_path, path])
        else:
            run(["cp", temp_path, path])
        run(["rm", temp_path])
        return True

    @staticmethod
    def generate_key():
        """
        Generate a 16 byte hex key using cmscommon.crypto.
        Can be used after CMS is installed.
        """
        key_command = "import cmscommon.crypto;" + \
                      "print cmscommon.crypto.get_hex_random_key()"
        key_output, _ = run_with_io(["python2", "-c", key_command])
        return key_output.strip()


class Installer():
    """
    An object for installation and configuration of components.
    """

    @staticmethod
    def install_custom_ubuntu_deps():
        """
        Install custom dependencies.
        """
        packages = [
            "nano",
            "git",
            "zip",
            "unzip",
            "valgrind",
            "pari-gp",          # Calculator
            "wget",
            "curl",
            "screen",
            "tmux",
            "mono-mcs",         # Mono C# compiler
            "python2.7",
            "ipython",          # Better python shell.
            "ipython3",
            "pyflakes",         # Python validator.
            "pyflakes3",
            "pep8",
            "python-flufl.lock",
            "python-networkx",
        ]
        run(["sudo", "apt-get", "install"] + packages)
        return True

    @staticmethod
    def install_ohmyzsh():
        """
        Install zsh and oh-my-zsh.
        """

        # Install manually, because the automated script of this repository
        # invokes a shell which would pause this script.
        run(["sudo", "apt-get", "install", "zsh"])
        zsh_url = "https://github.com/robbyrussell/oh-my-zsh.git"
        zsh_path = os.path.join(home_dir, ".oh-my-zsh")
        config_path = os.path.join(home_dir, ".zshrc")
        default_config_path = os.path.join(zsh_path, "templates/"
                                                     "zshrc.zsh-template")

        run(["git", "clone", zsh_url, zsh_path])
        run(["cp", default_config_path, config_path])

        choice = prompt("Change this user's default shell to zsh?",
                        ["yes", "no"])
        if choice == "yes":
            run(["chsh", "-s", "/bin/zsh"])

        highlight_url = "https://github.com/zsh-users/" +\
                        "zsh-syntax-highlighting.git"
        highlight_path = os.path.join(zsh_path, "custom/plugins/"
                                                "zsh-syntax-highlighting")
        run(["git", "clone", highlight_url, highlight_path])
        run(["sudo", "apt-get", "install", "source-highlight"])
        return True

    @staticmethod
    def setup_custom_config():
        """
        Download and replace each file in the custom_config_files
        dictionary. It is assumed each value is a dictionary with fields
        "url" and "path".
        """
        for config in custom_config_files:
            url = custom_config_files[config]["url"]
            path = custom_config_files[config]["path"]
            if os.path.exists(path):
                choice = prompt("%s exists, continue?" % path, ["yes", "no"])
                if choice != "yes":
                    return False
            run(["wget", url, "-O", path])
        return True

    @staticmethod
    def install_cms_deps():
        """
        Install the CMS Ubuntu dependencies with apt.
        """
        packages = [
            'build-essential',
            'openjdk-8-jre',
            'openjdk-8-jdk',
            'fpc',
            'postgresql',
            'postgresql-client',
            'gettext',
            'python2.7',
            'iso-codes',
            'shared-mime-info',
            'stl-manual',
            'cgroup-lite',
            'libcap-dev',
            'python-dev',
            'libpq-dev',
            'libcups2-dev',
            'libyaml-dev',
            'libffi-dev',
            'python-pip',
            'nginx-full',
            'fp-compiler',
            'fp-units-base',
            'fp-units-fcl',
            'fp-units-misc',
            'fp-units-math',
            'fp-units-rtl',
            'gcj-jdk',
            'haskell-platform',
            'rustc',
            'php7.0-cli',
            'php7.0-fpm',
        ]
        run(["sudo", "apt-get", "install"] + packages)
        return True

    @staticmethod
    def define_cms_dir():
        """
        Define Github related directories, like /home/ioi/Github/ioi-israel/cms
        If the Github directory is not defined yet, prompt for it.
        """
        global repo_dir, git_dir, cms_dir
        if cms_dir is not None:
            return
        git_dir = prompt_dir("Absolute path to github dir:",
                             must_exist=False, must_not_exist=False,
                             create=True, default=default_git_dir)
        repo_dir = os.path.join(git_dir, repo_name)
        if not os.path.isdir(repo_dir):
            os.makedirs(repo_dir)
        cms_dir = os.path.join(repo_dir, "cms")

    @staticmethod
    def change_to_cms_dir():
        """
        Change the working directory to the CMS directory.
        """
        os.chdir(cms_dir)

    @staticmethod
    def clone_cms():
        """
        Clone CMS into the defined CMS directory.
        Checkout the defined CMS branch and isolate branch.
        """
        Installer.define_cms_dir()
        run(["git", "clone", "--recursive", cms_url, cms_dir])
        Installer.change_to_cms_dir()
        run(["git", "checkout", cms_branch])
        os.chdir("isolate")
        run(["git", "checkout", isolate_branch])
        return True

    @staticmethod
    def run_cms_prerequisites():
        """
        Run the CMS prerequisites script.
        Among other things, this adds the user to the cmsuser group.
        If the user has not logged out and back in to apply this,
        let them know and stop.
        """
        Installer.define_cms_dir()
        Installer.change_to_cms_dir()
        script_path = os.path.join(cms_dir, "prerequisites.py")
        run(["sudo", script_path, "install"])

        groups_text, _ = run_with_io(["groups"])
        groups = groups_text.split()
        if "cmsuser" not in groups:
            info("[Prerequisites done, now log out and back in "
                 "to apply new user group. Interrupting now]")
            return False
        return True

    @staticmethod
    def install_cms_python_deps():
        """
        Install CMS Python dependencies using pip2.
        """
        Installer.define_cms_dir()
        Installer.change_to_cms_dir()
        requirements_path = os.path.join(cms_dir, "requirements.txt")
        run(["sudo", "pip2", "install", "-r", requirements_path])
        dev_requirements_path = os.path.join(cms_dir, "dev-requirements.txt")
        run(["sudo", "pip2", "install", "-r", dev_requirements_path])
        return True

    @staticmethod
    def run_cms_setup():
        """
        Run the CMS setup script.
        """
        Installer.define_cms_dir()
        Installer.change_to_cms_dir()
        script_path = os.path.join(cms_dir, "setup.py")
        run(["sudo", "python2", script_path, "install"])
        return True

    @staticmethod
    def setup_cms_db():
        """
        Create the database and its user.
        """
        postgres_commands = [
            "createuser --username=postgres --pwprompt cmsuser",
            "createdb --username=postgres --owner=cmsuser cmsdb "
            "--encoding='UTF8' --locale='en_US.UTF-8' --template=template0",
            "psql --username=postgres --dbname=cmsdb "
            "--command='ALTER SCHEMA public OWNER TO cmsuser'",
            "psql --username=postgres --dbname=cmsdb "
            "--command='GRANT SELECT ON pg_largeobject TO cmsuser'",

            # Testing DB
            "createdb --username=postgres --owner=cmsuser cmsdbfortesting "
            "--encoding='UTF8' --locale='en_US.UTF-8' --template=template0",
            "psql --username=postgres --dbname=cmsdbfortesting "
            "--command='ALTER SCHEMA public OWNER TO cmsuser'",
            "psql --username=postgres --dbname=cmsdbfortesting "
            "--command='GRANT SELECT ON pg_largeobject TO cmsuser'"
        ]
        commands_str = "&&".join(postgres_commands)
        run(["sudo", "su", "-", "postgres", "-c", commands_str])
        return True

    @staticmethod
    def customize_cms_config():
        """
        Download various CMS configuration templates from this repository,
        modify them as needed and install them to the appropriate paths.
        """
        Installer.define_cms_dir()
        choice = prompt("Override cms.conf, cms.ranking.conf, nginx.conf?",
                        ["yes", "no", "skip"])
        if choice == "skip":
            info("[Skipping]")
            return True
        elif choice == "no":
            return False

        # Local paths.
        conf_path = os.path.join(cms_dir, "config/cms.conf")
        ranking_conf_path = os.path.join(cms_dir, "config/cms.ranking.conf")
        nginx_conf_path = "/etc/nginx/nginx.conf"

        # URLs for downloading the templates.
        conf_url = repo_raw_url + "cms/cms.conf"
        ranking_conf_url = repo_raw_url + "cms/cms.ranking.conf"
        nginx_conf_url = repo_raw_url + "cms/nginx.conf"

        # Get the templates.
        conf = requests.get(conf_url).text
        ranking_conf = requests.get(ranking_conf_url).text
        nginx_conf = requests.get(nginx_conf_url).text

        # Change cms.conf database pasword.
        db_password = prompt_password("Database password yet again: ")
        conf = conf.replace("your_password_here", db_password)

        # Change cms.conf hex key.
        new_key = generate_key()
        old_key = "8e045a51e4b102ea803c06f92841a1fb"
        if old_key not in conf:
            fail("Expected %s to be in the repo cms.conf." % old_key)
            return False
        assert old_key != new_key
        conf = conf.replace(old_key, new_key)

        # Change cms.conf custom paths
        conf = conf.replace("INSTRUCTORS_PATH", instructors_path)
        conf = conf.replace("CONTESTANTS_PATH", contestants_path)

        # Change cms.conf and cms.ranking.conf password.
        ranking_password = generate_key()
        assert old_key != ranking_password
        conf = conf.replace("passw0rd", ranking_password)
        ranking_conf = ranking_conf.replace("passw0rd", ranking_password)

        # Write all files.
        write(conf_path, conf)
        write(ranking_conf_path, ranking_conf)
        write(nginx_conf_path, nginx_conf, sudo=True)

        # Apply the new nginx settings.
        run(["sudo", "nginx", "-s", "reload"])

        # Run the prerequisites again, in order to install the
        # new CMS configuration files.
        return Installer.run_cms_prerequisites()

    @staticmethod
    def swap_off():
        """
        Turn off swap in the system.
        """
        run(["sudo", "swapoff", "-a"])
        return True

    @staticmethod
    def cms_test():
        """
        Initialize the database, run the CMS test suite, then drop it.
        """
        Installer.define_cms_dir()
        Installer.change_to_cms_dir()

        choice = prompt("Warning: init the CMS database?",
                        ["yes", "no"])
        if choice == "yes":
            run(["cmsInitDB"])
        else:
            return False

        run(["cmsRunTests"])

        choice = prompt("Warning: DROP the CMS database?",
                        ["yes", "no"])
        if choice == "yes":
            run(["cmsDropDB"])
        else:
            return False

        return True

    @staticmethod
    def cms_init_db():
        """
        Initialize the CMS database (after it's created).
        """
        run(["cmsInitDB"])
        return True

    @staticmethod
    def cms_add_admin():
        """
        Add a user to the cmsAdminWebServer.
        """
        aws_usr = str(input("AWS user:"))
        aws_password = prompt_password("AWS password:")
        run(["cmsAddAdmin", aws_usr, "-p", aws_password])
        return True

    @staticmethod
    def install_gitolite():
        """
        Install gitolite3.
        """
        run(["sudo", "apt-get", "install", "gitolite3"])
        return True


# Put common functionality in the global scope, for less cluttered use.
info = Log.info
fail = Log.fail
warn = Log.warn
prompt = Log.prompt
prompt_dir = Log.prompt_dir
prompt_password = Log.prompt_password

run = Runner.run
run_with_io = Runner.run_with_io
write = Runner.write
generate_key = Runner.generate_key

# Local paths.
home_dir = os.path.expanduser("~")
default_git_dir = os.path.join(home_dir, "Github")
git_dir = None
repo_dir = None
cms_dir = None
instructors_path = os.path.join(home_dir, "for-instructors")
contestants_path = os.path.join(home_dir, "for-contestants")

# Repository information.
repo_name = "ioi-israel"
repo_raw_url = "https://raw.githubusercontent.com/ioi-israel/" +\
               "server-setup/master/"
cms_url = "https://github.com/ioi-israel/cms.git"
cms_branch = "v1.3-israel"
isolate_branch = "c8b0eef"

# Custom configuration files.
custom_config_files = {
    "nano": {
        "url": repo_raw_url + "custom/nano/.nanorc",
        "path": os.path.join(home_dir, ".nanorc")
    },
    "zsh": {
        "url": repo_raw_url + "custom/zsh/.zshrc",
        "path": os.path.join(home_dir, ".zshrc")
    },
    "screen": {
        "url": repo_raw_url + "custom/screen/.screenrc",
        "path": os.path.join(home_dir, ".screenrc")
    }
}

# Installation steps. Each has a description and a corresponding function.
steps = [
    {"text": "Installing custom Ubuntu packages",
     "function": Installer.install_custom_ubuntu_deps},
    {"text": "Installing zsh, and oh-my-zsh from Github",
     "function": Installer.install_ohmyzsh},
    {"text": "Downloading custom config files",
     "function": Installer.setup_custom_config},
    {"text": "Installing CMS Ubuntu dependencies",
     "function": Installer.install_cms_deps},
    {"text": "Cloning CMS",
     "function": Installer.clone_cms},
    {"text": "Running CMS prerequisites",
     "function": Installer.run_cms_prerequisites},
    {"text": "Installing CMS Python dependencies",
     "function": Installer.install_cms_python_deps},
    {"text": "Running CMS setup",
     "function": Installer.run_cms_setup},
    {"text": "Creating database user",
     "function": Installer.setup_cms_db},
    {"text": "Customizing CMS and server config",
     "function": Installer.customize_cms_config},
    {"text": "Turning off swap",
     "function": Installer.swap_off},
    {"text": "Running CMS tests (may take a while)",
     "function": Installer.cms_test},
    {"text": "Initializing CMS database",
     "function": Installer.cms_init_db},
    {"text": "Adding CMS admin.",
     "function": Installer.cms_add_admin},
    {"text": "Installing gitolite",
     "function": Installer.install_gitolite},
]


def main():
    """
    Run the program by executing the steps sequentially.
    """
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--start",
                        help="step to start with (between 1 and %d)." %
                        len(steps), type=int)
    parser.add_argument("-o", "--one",
                        help="execute just one step.",
                        action="store_true")
    parser.add_argument("-i", "--interact",
                        help="interactivity level: "
                             "1 confirms critical points, "
                             "2 confirms steps too (default), "
                             "3 confirms everything",
                        choices=["1", "2", "3"])

    args = parser.parse_args()
    start_range = 0
    end_range = len(steps)
    interact = 2

    # Start from a given step. Note indices are 1-based for the user.
    if args.start is not None:
        start_range = int(args.start) - 1
        if start_range < 0 or start_range >= len(steps):
            parser.error("[Step %d doesn't exist, exiting]" %
                         (start_range + 1))
        info("[Starting from step %d]" % (start_range + 1,))
    else:
        info("[Starting from the beginning]")

    # Execute just one step and exit.
    if args.one:
        end_range = start_range + 1

    # Set interactivity level.
    if args.interact is not None:
        interact = int(args.interact)

    Runner.set_interact(interact)

    # Run all requested steps, stop on failure.
    for index in range(start_range, end_range):
        success = Runner.run_step(index + 1, steps[index], len(steps))
        if not success:
            return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
