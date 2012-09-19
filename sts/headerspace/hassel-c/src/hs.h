#ifndef _HS_H_
#define _HS_H_

#include "array.h"

struct hs_vec {
  array_t **elems;
  struct hs_vec *diff;
  int used, alloc;
};

struct hs {
  int len;
  struct hs_vec list;
};

struct hs *hs_create  (int len);
void       hs_destroy (struct hs *hs);
void       hs_free    (struct hs *hs);

void       hs_copy   (struct hs *dst, const struct hs *src);
struct hs *hs_copy_a (const struct hs *src);
void       hs_print  (const struct hs *hs);
char      *hs_to_str (const struct hs *hs);

void hs_add  (struct hs *hs, array_t *a);
void hs_diff (struct hs *hs, const array_t *a);

bool hs_compact   (struct hs *hs);
void hs_comp_diff (struct hs *hs);
void hs_cmpl      (struct hs *hs);
bool hs_isect     (struct hs *a, const struct hs *b);
bool hs_isect_arr (struct hs *dst, const struct hs *src, const array_t *arr);
void hs_minus     (struct hs *a, const struct hs *b);
void hs_rewrite   (struct hs *hs, const array_t *mask, const array_t *rewrite);

#endif

