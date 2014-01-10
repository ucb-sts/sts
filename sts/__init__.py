# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import os
from datetime import date

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "pox"))
sys.path.append(os.path.join(os.path.dirname(__file__), "hassel/hsa-python"))

def check_sw_version(path, remote_branch):
  ''' Return whether the latest commit of the git repo located at the
      given path is the same as the remote repo's remote_branch.
  '''
  def get_version(branch="HEAD"):
    return os.popen("git rev-parse %s" % branch).read()

  old_cwd = os.getcwd()
  try:
    os.chdir(path)
    if os.system("git fetch") != 0:
      raise IOError("Unable to fetch from origin for repo %s" % path)
    local_version = get_version()
    remote_version = get_version(branch=remote_branch)
    return local_version == remote_version
  except Exception as e:
    print >> sys.stderr, ('''Unable to check whether software versions are '''
                          '''up-to-date: %s''' % e)
  finally:
    os.chdir(old_cwd)

def check_dependencies():
  '''
  Double check whether POX and Hassel are at the latest software versions.
  '''
  print >> sys.stderr, "Checking software versions..."
  pox_path = os.path.join(os.path.dirname(__file__), "..", "pox")
  if not check_sw_version(pox_path, "remotes/origin/debugger"):
    print >> sys.stderr, ('''Warning: POX version not up-to-date. You should '''
                          '''probably run:\n $ (cd pox; git pull) ''')

  hassel_path = os.path.join(os.path.dirname(__file__), "hassel")
  if not os.path.exists(os.path.join(hassel_path, "LICENSE.txt")):
    print >> sys.stderr, "Warning: Hassel submodule not loaded."
  elif not check_sw_version(hassel_path, "remotes/origin/HEAD"):
    print >> sys.stderr, ('''Warning: Hassel version not up-to-date. You should '''
                          '''probably run:\n $ git submodule update ''')

# We store the last date we checked software versions in sts/last-version-check.
# The format of the file is: date.today().toordinal()
timestamp_path = os.path.join(os.path.dirname(__file__), "last-version-check")

def checked_recently():
  ''' Return whether we have checked dependencies in the last day. '''
  if not os.path.exists(timestamp_path):
    return False

  current_date = date.today()
  with open(timestamp_path) as timestamp_file:
    try:
      last_check_date = date.fromordinal(int(timestamp_file.read()))
    except:
      # Possible corruption.
      return False
    return last_check_date == current_date

def write_new_timestamp():
  with open(timestamp_path, "w") as timestamp_file:
    current_date = date.today()
    timestamp_file.write(str(current_date.toordinal()))

# We only check dependencies once a day, since `git fetch` takes a fair amount of
# time.
if not checked_recently():
  check_dependencies()
  write_new_timestamp()
