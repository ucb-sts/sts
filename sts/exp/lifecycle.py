import getpass
import os
import re
import socket
import sys
import json
from sts.util.convenience import timestamp_string
import logging
import subprocess

log = logging.getLogger("sts.exp_lifecycle")

sts_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

sts_modules = ( ("sts", sts_path),
                ("pox", sts_path + "/pox")
                )

def dump_metadata(metadata_file):
  with open(metadata_file, "w") as t:
    metadata = { 'timestamp' : timestamp_string(),
               'argv' : sys.argv,
               'user' : getpass.getuser(),
               'cwd' : os.getcwd(),
               'host' : socket.gethostname(),
               'modules' : {
                 module : { 'commit' : backtick("git rev-parse HEAD", cwd=path),
                            'branch' : backtick("git rev-parse --abbrev-ref HEAD", cwd=path)
                          } for module, path in sts_modules
               }
             }
    t.write(json.dumps(metadata, sort_keys=True, indent=2, separators=(',', ": ")) + "\n")

def guess_config_name(config):
  parts = config.__name__.split(".")
  while parts[0] == "config" or parts[0] == "exp":
    parts = parts[1:]

  if parts[-1] == "orig_config":
    del parts[-1]

  parts[-1] = re.sub(r'_conf(ig)?$', '', parts[-1])
  return "_".join(parts)

def walk_dirs_up(path):
  while path != "" and path != "/":
    yield path
    path = os.path.dirname(path)

def find(f, iterable):
  for i in iterable:
    if f(i):
      return i
  return None

def find_git_dir(results_dir):
  return find(lambda f: os.path.exists(os.path.join(f, ".git" )), walk_dirs_up(results_dir))

def backtick(cmd, *args, **kwargs):
  return subprocess.Popen(cmd, *args, shell=True, stdout=subprocess.PIPE, **kwargs).stdout.read().strip()

def system(cmd, *args, **kwargs):
  return subprocess.call(cmd, *args, shell=True, **kwargs)

def git_has_uncommitted_files(d):
  return system("git diff-files --quiet --ignore-submodules --", cwd=d) > 0 \
    or system("git diff-index --cached --quiet HEAD --ignore-submodules --", cwd=d) > 0

def publish_prepare(exp_name, results_dir):
  for module, path in sts_modules:
    if git_has_uncommitted_files(path):
      raise Exception("Cannot publish: uncommitted changes in sts module %s" % module)

  res_git_dir = find_git_dir(results_dir)
  if not res_git_dir:
    raise Exception("Cannot publish - no git dir found in results tree")
  if git_has_uncommitted_files(res_git_dir):
      raise Exception("Cannot publish: uncommitted changes in sts module %s" % res_git_dir)

def publish_results(exp_name, results_dir):
    res_git_dir = find_git_dir(results_dir)
    rel_results_dir = os.path.relpath(results_dir, res_git_dir)
    log.info("Publishing results to git dir "+res_git_dir)
    system("git add %s" % rel_results_dir, cwd=res_git_dir)
    system("git commit -m '%s'" % exp_name, cwd=res_git_dir)
    system("git pull --rebase", cwd=res_git_dir)
    system("git push", cwd=res_git_dir)
