#include "parse.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int
main (int argc, char **argv)
{
  struct tf *(*fn) (const char *) = parse_simple;
  if (!strcmp (argv[1], "tf")) { argv++; fn = parse_tf; }
  struct tf *tf = fn (argv[1]);
  printf ("\n");
  tf_print (tf);

  struct hs *hs = hs_create (tf->len);
  hs_add (hs, array_create (hs->len, BIT_X));
  struct tf_res *res = tf_apply (tf, hs, atoi(argv[2]), false);
  tf_res_print (res, true);

  tf_res_free (res);
  hs_free (hs);
  tf_free (tf);
  return 0;
}

