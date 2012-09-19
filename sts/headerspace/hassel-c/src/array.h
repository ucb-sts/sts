#ifndef _ARRAY_H_
#define _ARRAY_H_

#include "util.h"

#if __x86_64 || __amd64 || _M_X64
typedef uint64_t array_t;
#else
typedef uint32_t array_t;
#endif

enum bit_val { BIT_Z = 0, BIT_0, BIT_1, BIT_X, BIT_UNDEF };

#define ARRAY_BYTES(L) ( ROUND_UP (2 * (L), sizeof (array_t)) )

array_t *array_create   (int len, enum bit_val val);
void     array_free     (array_t *a);

array_t *array_copy     (const array_t *a, int len);
array_t *array_from_str (const char *s);
char    *array_to_str   (const array_t *a, int len, bool decimal);

bool array_has_x  (const array_t *a, int len);
bool array_has_z  (const array_t *a, int len);
bool array_is_eq  (const array_t *a, const array_t *b, int len);
/* True if B is a subset of A. */
bool array_is_sub (const array_t *a, const array_t *b, int len);

void array_and     (const array_t *a, const array_t *b, int len, array_t *res);
bool array_cmpl    (const array_t *a, int len, int *n, array_t **res);
bool array_diff    (const array_t *a, const array_t *b, int len, int *n, array_t **res);
bool array_isect   (const array_t *a, const array_t *b, int len, array_t *res);
void array_not     (const array_t *a, int len, array_t *res);
void array_or      (const array_t *a, const array_t *b, int len, array_t *res);
int  array_rewrite (array_t *a, const array_t *mask, const array_t *rewrite, int len);
int  array_x_count (const array_t *a, const array_t *mask, int len);  // counts number of X bits in positions masked by a 0

array_t  *array_and_a   (const array_t *a, const array_t *b, int len);
array_t **array_cmpl_a  (const array_t *a, int len, int *n);
array_t **array_diff_a  (const array_t *a, const array_t *b, int len, int *n);
array_t  *array_isect_a (const array_t *a, const array_t *b, int len);
array_t  *array_not_a   (const array_t *a, int len);
array_t  *array_or_a    (const array_t *a, const array_t *b, int len);

#endif

