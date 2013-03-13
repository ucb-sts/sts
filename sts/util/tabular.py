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

class Tabular(object):
  def __init__(self, *cols):
    self.cols = cols

  def show(self, data):
    cols = self.cols
    titles = [c[0] for c in cols]
    vals = [ [str(c[1](d)) if d else "*" for c in cols] for d in data ]
    lengths = [ reduce(lambda m, v: max(m, len(v[i])), vals + [ titles], 0) for i,c in enumerate(cols) ]

    l = 1 + reduce(lambda l, s: l + s + 3, lengths, 0)

    row = lambda r: "| " + " | ".join( ("%"+str(lengths[i])+"s") % v for i,v in enumerate(r)) + " |"

    print "-" * l
    print row(titles)
    print "-" * l
    for v in vals:
      print row(v)
    print "-" * l


