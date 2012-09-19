
static struct tf_res *
rule_fwd_rw_inv (const struct rule *r, const struct hs *hs, int port,
                 struct tf_res **tailp)
{
  const array_t *match = r->inv_match ? r->inv_match : r->match;
  struct hs copy;
  if (!hs_isect_arr (&copy, hs, match)) {
    return *tailp = NULL;
  }
  struct tf_res *res = NULL, *tail = NULL;

  if (r->mask) {
    //list_rewrite (&copy.add, r->mask, r->inv_rewrite, hs->len);
    //list_rewrite (&copy.diff, r->mask, r->inv_rewrite, hs->len);
  }

  for (int i = 0; i < r->nin; i++) {
    struct tf_res *tmp = tf_res_create (r, &copy, r->in[i]);

    diff_deps (&tmp->hs, r->in[i], r->deps, NULL, 0);
    if (hs_compact (&tmp->hs)) {
      if (tail) tail->next = tmp;
      else res = tmp;
      tail = tmp;
    } else tf_res_free (tmp);
  }
  hs_destroy (&copy);
  *tailp = tail;
  return res;
}

