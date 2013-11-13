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

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "pox"))
sys.path.append(os.path.join(os.path.dirname(__file__), "hassel/hsa-python"))

# TODO(cs): only run this every every few hours or so, not for every run of
# simulator.

def check_sw_version(path, remote_branch):
  ''' Return whether the latest commit of the git repo located at the
      given path is the same as the remote repo's remote_branch.
  '''
  def get_version(branch=""):
    return os.popen("git show %s | head -1 | cut -d ' ' -f2" % branch).read()

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

# Double check the first time STS is loaded whether we have the latest
# software versions.
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
