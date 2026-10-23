import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, UNAUTHORIZED_EVENT, api, errorDetail, fmtDay, fmtMoney, fmtPaise, post } from "@/lib/api";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("errorDetail", () => {
  it("reads string details", () => {
    expect(errorDetail({ detail: "Plan not found" })).toBe("Plan not found");
  });
  it("flattens FastAPI validation errors", () => {
    const body = { detail: [{ loc: ["body", "justification"], msg: "too short" }] };
    expect(errorDetail(body)).toBe("justification: too short");
  });
  it("falls back for unknown shapes", () => {
    expect(errorDetail(null)).toBe("Request failed");
  });
});

describe("fmtMoney", () => {
  it("formats rupees with Indian grouping", () => {
    expect(fmtMoney(7813000)).toBe("₹78,13,000");
  });
});

describe("fmtPaise", () => {
  it("shows integer paise as rupees", () => {
    expect(fmtPaise(49405100)).toBe("₹4,94,051");
    expect(fmtPaise(49405150, 2)).toBe("₹4,94,051.50");
  });
  it("shows a dash for missing or masked amounts", () => {
    expect(fmtPaise(null)).toBe("–");
    expect(fmtPaise(undefined)).toBe("–");
  });
});

describe("fmtDay", () => {
  it("treats date-only strings as local dates", () => {
    expect(fmtDay("2026-11-24")).toBe("24 Nov 2026");
  });
  it("shows a dash when empty", () => {
    expect(fmtDay(null)).toBe("–");
  });
});

describe("api", () => {
  it("prefixes /api, sends JSON and returns the body", async () => {
    const fetch = mockFetch(200, { id: 1 });
    await expect(post("/plans", { name: "x" })).resolves.toEqual({ id: 1 });
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/plans");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(init.credentials).toBe("same-origin");
  });

  it("returns undefined for 204", async () => {
    mockFetch(204, undefined);
    await expect(api("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("throws ApiError with the server detail", async () => {
    mockFetch(409, { detail: "Plan is approved; only drafts can be changed" });
    const err = (await api("/plans/1/run").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.message).toMatch(/only drafts/);
  });

  it("announces a 401 so the app can return to login", async () => {
    const dispatch = vi.fn();
    vi.stubGlobal("window", { dispatchEvent: dispatch });
    mockFetch(401, { detail: "Not signed in" });
    await api("/plans").catch(() => {});
    expect(dispatch).toHaveBeenCalledOnce();
    expect((dispatch.mock.calls[0][0] as Event).type).toBe(UNAUTHORIZED_EVENT);
  });

  it("does not announce a 401 from the login endpoint itself", async () => {
    const dispatch = vi.fn();
    vi.stubGlobal("window", { dispatchEvent: dispatch });
    mockFetch(401, { detail: "Invalid email or password" });
    await post("/auth/login", {}).catch(() => {});
    expect(dispatch).not.toHaveBeenCalled();
  });
});
