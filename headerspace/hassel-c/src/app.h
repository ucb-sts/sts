#ifndef _APP_H_
#define _APP_H_

#include "res.h"

void app_init (void);
void app_fini (void);

/* Reachability of HS from IN to OUT. If OUT == NULL, computes reachability to
   all output ports. */
struct list_res reachability (const struct hs *hs, uint32_t in, const uint32_t *out, int nout);

#endif

