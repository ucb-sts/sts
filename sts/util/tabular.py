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


