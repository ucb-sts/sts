#include "app.h"
#include "data.h"
#include <libgen.h>
#include <limits.h>
#include <sys/time.h>
//#include <valgrind/callgrind.h>

#ifndef NTF_STAGES
#define NTF_STAGES 1
#endif

static inline int64_t
diff (struct timeval *a, struct timeval *b)
{
  int64_t x = (int64_t)a->tv_sec * 1000000 + a->tv_usec;
  int64_t y = (int64_t)b->tv_sec * 1000000 + b->tv_usec;
  return x - y;
}

static void
unload (void)
{ data_unload (); }


static void
load (char *argv0)
{
  fflush (stdout);

  char name[PATH_MAX + 1];
  snprintf (name, sizeof name, "data/%s.dat", basename (argv0));
  data_load (name);
  if (atexit (unload)) errx (1, "Failed to set exit handler.");
}

int
main (int argc, char **argv)
{
  //CALLGRIND_TOGGLE_COLLECT;
  if (argc < 2) {
    fprintf (stderr, "Usage: %s <in_port> [<out_ports>...]\n", argv[0]);
    exit (1);
  }

  load (argv[0]);
  app_init ();

  struct hs hs;
  memset (&hs, 0, sizeof hs);
  hs.len = data_arrs_len;
  hs_add (&hs, array_create (hs.len, BIT_X));

  int nout = argc - 2;
  uint32_t out[nout];
  for (int i = 0; i < nout; i++) out[i] = atoi (argv[i + 2]);

  //CALLGRIND_TOGGLE_COLLECT;
  struct timeval start, end;
  gettimeofday (&start, NULL);
  struct list_res res = reachability (&hs, atoi (argv[1]), nout ? out : NULL, nout);
  gettimeofday (&end, NULL);
  //CALLGRIND_TOGGLE_COLLECT;

  list_res_print (&res);
  fprintf (stderr, "Time: %" PRId64 " us\n", diff (&end, &start));

  list_res_free (&res);
  hs_destroy (&hs);
  app_fini ();
  return 0;
}

