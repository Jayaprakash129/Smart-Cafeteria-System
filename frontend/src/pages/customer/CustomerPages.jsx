import { useEffect, useState } from "react";
import { api, money, num } from "../../api";
import Layout from "../../components/Layout";
import { Badge, Card, ErrorBox, Loading, Stat, Table } from "../../components/ui";

/* ----------------------------------------------------------------- Menu */
export function CustomerMenu() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [cart, setCart] = useState({});
  const [placing, setPlacing] = useState(false);
  const [placed, setPlaced] = useState(null);
  const [cat, setCat] = useState("all");

  const load = () => api.get("/customer/menu").then(setData).catch(setError);
  useEffect(() => {
    load();
  }, []);

  const add = (id, d = 1) =>
    setCart((c) => {
      const n = { ...c, [id]: Math.max(0, (c[id] || 0) + d) };
      if (!n[id]) delete n[id];
      return n;
    });

  const items = (data?.items || []).filter((i) => cat === "all" || i.category === cat);
  // The trial offer discounts exactly one unit per order (see
  // routers/customer.py place_order) -- any additional units of that dish
  // are charged the normal price, so the cart preview must match or the
  // total shown here would disagree with what checkout actually charges.
  const cartLines = Object.entries(cart).map(([id, qty]) => {
    const dish = data.items.find((i) => i.dish_id === Number(id));
    const fullPrice = dish?.price ?? 0;
    const offerPrice = dish?.offer?.offer_price;
    const discountedUnits = offerPrice != null ? Math.min(1, qty) : 0;
    const line =
      discountedUnits * offerPrice + (qty - discountedUnits) * fullPrice;
    return { dish, qty, price: offerPrice ?? fullPrice, discountedUnits, line };
  });
  const total = cartLines.reduce((s, l) => s + l.line, 0);

  const order = async () => {
    setPlacing(true);
    setError(null);
    try {
      const res = await api.post("/customer/orders", {
        items: Object.entries(cart).map(([dish_id, quantity]) => ({
          dish_id: Number(dish_id),
          quantity,
        })),
      });
      setPlaced(res);
      setCart({});
      await load();
      setTimeout(() => setPlaced(null), 5000);
    } catch (e) {
      setError(e);
    } finally {
      setPlacing(false);
    }
  };

  const offers = (data?.items || []).filter((i) => i.offer);

  return (
    <Layout title="Today's Menu" subtitle={data ? `${data.institution} · ${data.date}` : ""}>
      <ErrorBox error={error} onRetry={load} />
      {!data ? (
        <Loading />
      ) : (
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            {offers.length > 0 && (
              <div className="card card-pad border-brand-300 bg-gradient-to-r from-brand-50 to-white">
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-lg">🎁</span>
                  <h3 className="font-semibold text-brand-800">
                    Just for you — {offers.length} personalised offer
                    {offers.length === 1 ? "" : "s"}
                  </h3>
                </div>
                <div className="flex flex-wrap gap-2">
                  {offers.map((o) => (
                    <div key={o.dish_id} className="rounded-lg border border-brand-200 bg-white px-3 py-2">
                      <div className="text-sm font-medium text-slate-800">{o.name}</div>
                      <div className="text-sm">
                        <span className="text-slate-400 line-through">{money(o.offer.original_price)}</span>{" "}
                        <span className="font-semibold text-brand-700">{money(o.offer.offer_price)}</span>{" "}
                        <Badge tone="brand">−{o.offer.discount_pct}%</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {placed && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                Order #{placed.order_id} placed — {money(placed.total_amount)}. Collect at the counter.
              </div>
            )}

            <div className="flex flex-wrap gap-1.5">
              {["all", ...(data.categories || [])].map((c) => (
                <button
                  key={c}
                  onClick={() => setCat(c)}
                  className={`rounded-full px-3.5 py-1.5 text-sm transition-colors ${
                    cat === c
                      ? "bg-brand-600 text-white"
                      : "bg-white text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {items.map((i) => (
                <div key={i.dish_id} className="card card-pad">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={i.is_veg ? "text-emerald-600" : "text-rose-600"}>
                          {i.is_veg ? "🟢" : "🔴"}
                        </span>
                        <h4 className="truncate font-medium text-slate-800">{i.name}</h4>
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                        <span>{i.category}</span>
                        {i.avg_rating && <span>★ {i.avg_rating}</span>}
                        {i.recommended && <Badge tone="brand">chef's pick #{i.recommendation_rank}</Badge>}
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      {i.offer ? (
                        <>
                          <div className="text-xs text-slate-400 line-through">{money(i.offer.original_price)}</div>
                          <div className="font-semibold text-brand-700">{money(i.offer.offer_price)}</div>
                        </>
                      ) : (
                        <div className="font-semibold text-slate-900">{money(i.price)}</div>
                      )}
                    </div>
                  </div>

                  <div className="mt-3 flex items-center justify-end gap-2">
                    {cart[i.dish_id] ? (
                      <>
                        <button className="btn-ghost h-8 w-8 p-0" onClick={() => add(i.dish_id, -1)}>−</button>
                        <span className="w-6 text-center text-sm font-medium">{cart[i.dish_id]}</span>
                        <button className="btn-primary h-8 w-8 p-0" onClick={() => add(i.dish_id, 1)}>+</button>
                      </>
                    ) : (
                      <button className="btn-primary px-3 py-1.5" onClick={() => add(i.dish_id, 1)}>
                        Add
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="lg:sticky lg:top-20 lg:self-start">
            <Card title="Your order" subtitle={`${cartLines.length} item(s)`}>
              {cartLines.length === 0 ? (
                <p className="py-8 text-center text-sm text-slate-400">
                  Your cart is empty
                </p>
              ) : (
                <>
                  <div className="space-y-2">
                    {cartLines.map((l) => (
                      <div key={l.dish.dish_id} className="flex justify-between text-sm">
                        <span className="truncate text-slate-700">
                          {l.dish.name} × {l.qty}
                          {l.dish.offer && <Badge tone="brand"> offer</Badge>}
                        </span>
                        <span className="ml-2 shrink-0 tabular-nums text-slate-800">
                          {money(l.line)}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 flex justify-between border-t border-slate-200 pt-3">
                    <span className="font-medium text-slate-700">Total</span>
                    <span className="text-lg font-semibold text-slate-900">{money(total)}</span>
                  </div>
                  <button className="btn-primary mt-4 w-full" disabled={placing} onClick={order}>
                    {placing ? "Placing…" : "Place order"}
                  </button>
                </>
              )}
            </Card>
          </div>
        </div>
      )}
    </Layout>
  );
}

/* --------------------------------------------------------------- Offers */
export function CustomerOffers() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get("/customer/offers").then(setRows).catch(setError);
  }, []);

  return (
    <Layout title="My Offers" subtitle="Personalised trial discounts">
      <ErrorBox error={error} />
      {!rows ? (
        <Loading />
      ) : rows.length === 0 ? (
        <Card>
          <p className="py-10 text-center text-sm text-slate-400">
            No offers yet. Offers appear when a dish you haven't tried becomes a best seller.
          </p>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((o) => (
            <div
              key={o.id}
              className={`card card-pad ${o.is_active ? "border-brand-300" : "opacity-60"}`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <h4 className="font-medium text-slate-800">{o.dish_name}</h4>
                  <div className="text-xs text-slate-400">{o.offer_date}</div>
                </div>
                <Badge tone={o.status === "redeemed" ? "blue" : o.is_active ? "green" : "slate"}>
                  {o.status}
                </Badge>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-slate-400 line-through">{money(o.original_price)}</span>
                <span className="text-xl font-semibold text-brand-700">{money(o.offer_price)}</span>
              </div>
              <div className="mt-1 text-sm text-emerald-600">
                Save {money(o.savings)} ({o.discount_pct}%)
              </div>
            </div>
          ))}
        </div>
      )}
    </Layout>
  );
}

/* --------------------------------------------------------------- Orders */
export function CustomerOrders() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [rated, setRated] = useState({});

  useEffect(() => {
    api.get("/customer/orders").then(setRows).catch(setError);
  }, []);

  const rate = async (dishId, rating) => {
    try {
      await api.post("/customer/feedback", { dish_id: dishId, rating });
      setRated((s) => ({ ...s, [dishId]: rating }));
    } catch (e) {
      setError(e);
    }
  };

  return (
    <Layout title="My Orders" subtitle="Order history and dish ratings">
      <ErrorBox error={error} />
      {!rows ? (
        <Loading />
      ) : (
        <div className="space-y-3">
          {rows.map((o) => (
            <Card key={o.order_id} title={`Order #${o.order_id}`} subtitle={`${o.date} · ${o.channel}`}>
              <div className="space-y-2">
                {o.items.map((i, idx) => (
                  <div key={idx} className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm text-slate-700">
                      {i.dish_name} × {i.quantity}
                      {i.discount_applied > 0 && (
                        <Badge tone="brand"> saved {money(i.discount_applied)}</Badge>
                      )}
                    </span>
                    <span className="flex items-center gap-3">
                      <span className="flex gap-0.5">
                        {[1, 2, 3, 4, 5].map((n) => (
                          <button
                            key={n}
                            onClick={() => rate(i.dish_id, n)}
                            className={`text-sm ${
                              (rated[i.dish_id] || 0) >= n ? "text-amber-400" : "text-slate-200"
                            } hover:text-amber-400`}
                          >
                            ★
                          </button>
                        ))}
                      </span>
                      <span className="w-16 text-right text-sm tabular-nums text-slate-600">
                        {money(i.unit_price * i.quantity)}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex justify-between border-t border-slate-100 pt-2.5">
                <span className="text-sm text-slate-500">Total</span>
                <span className="font-semibold text-slate-900">{money(o.total_amount)}</span>
              </div>
            </Card>
          ))}
          {!rows.length && (
            <Card>
              <p className="py-10 text-center text-sm text-slate-400">No orders yet.</p>
            </Card>
          )}
        </div>
      )}
    </Layout>
  );
}

/* -------------------------------------------------------------- Profile */
export function CustomerProfile() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get("/customer/profile").then(setData).catch(setError);
  }, []);

  const s = data?.stats_30d;

  return (
    <Layout title="Profile" subtitle={data?.institution?.name || ""}>
      <ErrorBox error={error} />
      {!data ? (
        <Loading />
      ) : (
        <div className="max-w-3xl space-y-5">
          <Card title={data.full_name} subtitle={data.email}>
            <dl className="grid gap-3 sm:grid-cols-2">
              <Row label="Phone" value={data.phone || "—"} />
              <Row label="Institution" value={data.institution?.name || "—"} />
              <Row label="Segment" value={data.institution?.segment || "—"} />
            </dl>
          </Card>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Orders (30d)" value={s.orders} />
            <Stat label="Total spend" value={money(s.total_spend)} sub={`avg ${money(s.avg_order_value)}`} />
            <Stat label="Offers received" value={s.offers_received} tone="brand" />
            <Stat label="Offers redeemed" value={s.offers_redeemed} tone="good" />
          </div>
        </div>
      )}
    </Layout>
  );
}

function Row({ label, value }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-800">{value}</dd>
    </div>
  );
}
