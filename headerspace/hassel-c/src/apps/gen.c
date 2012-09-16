#include "parse.h"

int
main (int argc, char **argv)
{
  if (argc < 2) {
    fprintf (stderr, "Usage: %s <network>\n", argv[0]);
    exit (1);
  }
  parse_dir ("data", "tfs", argv[1]);
  return 0;
}

