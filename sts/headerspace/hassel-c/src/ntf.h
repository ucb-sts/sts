#ifndef _NTF_H_
#define _NTF_H_

#include "res.h"

int             ntf_get_sw (uint32_t port);
struct list_res ntf_apply  (const struct res *in, int sw);

#endif

