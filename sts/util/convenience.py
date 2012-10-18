
def find(f, seq):
  """Return first item in sequence where f(item) == True."""
  for item in seq:
    if f(item):
      return item

def find_index(f, seq):
  """Return the index of the first item in sequence where f(item) == True."""
  for index, item in enumerate(seq):
    if f(item):
      return index

