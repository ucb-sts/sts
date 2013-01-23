BEGIN = '\033[1;'
END = '\033[1;m'

class color(object):
  GRAY, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, CRIMSON = map(lambda num : BEGIN + str(num) + "m", range(30, 39))
  B_GRAY, B_RED, B_GREEN, B_YELLOW, B_BLUE, B_MAGENTA, B_CYAN, B_WHITE, B_CRIMSON =  map(lambda num: BEGIN + str(num) + "m", range(40, 49))
  NORMAL = END

class msg():
  global_io_master = None

  BEGIN = '\033[1;'
  END = '\033[1;m'

  GRAY, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, CRIMSON = map(lambda num: str(num) + "m", range(30, 39))
  B_BLACK, B_RED, B_GREEN, B_YELLOW, B_BLUE, B_MAGENTA, B_CYAN, B_GRAY, B_CRIMSON =  map(lambda num: str(num) + "m", range(40, 49))

  @staticmethod
  def interactive(message):
    # todo: would be nice to simply give logger a color arg, but that doesn't exist...
    print msg.BEGIN + msg.WHITE + message + msg.END

  @staticmethod
  def event(message):
    print msg.BEGIN + msg.CYAN + message + msg.END

  @staticmethod
  def event_success(message):
    print msg.BEGIN + msg.GREEN + msg.BEGIN + msg.B_BLUE + message + msg.END

  @staticmethod
  def event_timeout(message):
    print msg.BEGIN + msg.RED + msg.BEGIN + msg.B_BLUE + message + msg.END

  @staticmethod
  def mcs_event(message):
    print msg.BEGIN + msg.B_MAGENTA + message + msg.END

  @staticmethod
  def raw_input(message):
    prompt = msg.BEGIN + msg.WHITE + message + msg.END
    if msg.global_io_master:
      s = msg.global_io_master.raw_input(prompt)
    else:
      s = raw_input(prompt)

    if s == "debug":
      import pdb
      pdb.set_trace()
    return s

  @staticmethod
  def success(message):
    print msg.BEGIN + msg.B_GREEN + msg.BEGIN + msg.WHITE + message + msg.END

  @staticmethod
  def fail(message):
    print msg.BEGIN + msg.B_RED + msg.BEGIN + msg.WHITE + message + msg.END

  @staticmethod
  def set_io_master(io_master):
    msg.global_io_master = io_master

  @staticmethod
  def unset_io_master():
    msg.global_io_master = None


