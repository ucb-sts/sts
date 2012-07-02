BEGIN = '\033[1;'
END = '\033[1;m'

class color(object):
  GRAY, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, CRIMSON = map(lambda num : BEGIN + str(num) + "m", range(30, 39))
  B_GRAY, B_RED, B_GREEN, B_YELLOW, B_BLUE, B_MAGENTA, B_CYAN, B_WHITE, B_CRIMSON =  map(lambda num: BEGIN + str(num) + "m", range(40, 49))
  NORMAL = END

class msg():
  BEGIN = '\033[1;'
  END = '\033[1;m'

  enabled = True # just a simple variable to control whether we should print anything at all
  # this is a hack until we properly fix the logging levels, which depend on how the simulator
  # will run non-interactively on ton of simulations

  GRAY, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, CRIMSON = map(lambda num: str(num) + "m", range(30, 39))
  B_GRAY, B_RED, B_GREEN, B_YELLOW, B_BLUE, B_MAGENTA, B_CYAN, B_WHITE, B_CRIMSON =  map(lambda num: str(num) + "m", range(40, 49))

  @staticmethod
  def interactive(message):
    # todo: would be nice to simply give logger a color arg, but that doesn't exist...
    if msg.enabled:
      print msg.BEGIN + msg.WHITE + message + msg.END

  @staticmethod
  def event(message):
    if msg.enabled:
      print msg.BEGIN + msg.CYAN + message + msg.END

  @staticmethod
  def raw_input(message):
    prompt = msg.BEGIN + msg.WHITE + message + msg.END
    return raw_input(prompt)

  @staticmethod
  def success(message):
    if msg.enabled:
      print msg.BEGIN + msg.B_GREEN + msg.BEGIN + msg.WHITE + message + msg.END

  @staticmethod
  def fail(message):
    if msg.enabled:
      print msg.BEGIN + msg.B_RED + msg.BEGIN + msg.WHITE + message + msg.END
