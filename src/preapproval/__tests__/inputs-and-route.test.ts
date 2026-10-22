import { AddressInfo } from "net";
import { Server } from "http";
import { config } from "../../config";
import { createServer } from "../../server";
import { decide, InvalidLeadError, preapprove } from "../index";
import { normalizeInputs, parseIsoDate, toNumber } from "../inputs";
import { MODEL } from "../model";

const now = new Date("2026-10-22T00:00:00Z");

describe("input parsing", () => {
  it("accepts numbers and plain numeric strings only", () => {
    expect(toNumber(1500000)).toBe(1500000);
    expect(toNumber(" 720 ")).toBe(720);
    expect(toNumber("2.5")).toBe(2.5);
    for (const bad of [null, undefined, "", " ", false, true, [], [1500000], {}, "1,000", "0x10", "5+", NaN, Infinity]) {
      expect(toNumber(bad)).toBeNull();
    }
  });

  it("parses only real YYYY-MM-DD dates", () => {
    expect(parseIsoDate("2021-10-22")?.toISOString()).toBe("2021-10-22T00:00:00.000Z");
    for (const bad of ["2021-02-30", "1", "12", "10/22/2021", "2021-1-5", 2015, null, "2021-10-22T00:00:00Z"]) {
      expect(parseIsoDate(bad)).toBeNull();
    }
  });

  it("rejects missing revenue instead of scoring it as $0", () => {
    for (const annualRevenue of [null, "", false, [], undefined] as unknown[]) {
      expect(() => normalizeInputs({ annualRevenue: annualRevenue as number, creditScore: 760, timeInBusinessYears: 8 }, now)).toThrow(InvalidLeadError);
    }
    expect(() => normalizeInputs({ annualRevenue: 2e9, creditScore: 760, timeInBusinessYears: 8 }, now)).toThrow(InvalidLeadError);
  });

  it("falls back to the start date when TIB is blank, and rejects negative or future TIB", () => {
    const x = normalizeInputs({ annualRevenue: 1_500_000, creditScore: 760, timeInBusinessYears: "", businessStartDate: "2018-10-22" }, now);
    expect(x.timeInBusinessYears).toBeCloseTo(8, 2);
    expect(() => normalizeInputs({ annualRevenue: 1_500_000, creditScore: 760, timeInBusinessYears: -3 }, now)).toThrow(InvalidLeadError);
    expect(() => normalizeInputs({ annualRevenue: 1_500_000, creditScore: 760, businessStartDate: "2030-01-01" }, now)).toThrow(InvalidLeadError);
    expect(() => normalizeInputs({ annualRevenue: 1_500_000, creditScore: 760, businessStartDate: "1" }, now)).toThrow(InvalidLeadError);
    expect(() => normalizeInputs({ annualRevenue: 1_500_000, creditScore: 760, businessStartDate: "1899-12-31" }, now)).toThrow(InvalidLeadError);
  });

  it("rejects time in business over 100 years (a founding year or month count in the years field)", () => {
    for (const timeInBusinessYears of [2015, "2015", 101, 1e300]) {
      expect(() => normalizeInputs({ annualRevenue: 1_500_000, creditScore: 760, timeInBusinessYears }, now)).toThrow(InvalidLeadError);
    }
    expect(normalizeInputs({ annualRevenue: 1_500_000, creditScore: 760, timeInBusinessYears: 100 }, now).timeInBusinessYears).toBe(100);
  });

  it("treats credit scores outside 300-850 as missing", () => {
    expect(normalizeInputs({ annualRevenue: 9e5, creditScore: 851, timeInBusinessYears: 4 }, now).creditScore).toBeNull();
    expect(normalizeInputs({ annualRevenue: 9e5, creditScore: "850", timeInBusinessYears: 4 }, now).creditScore).toBe(850);
  });

  it("never reports an approval probability at or above the threshold on a threshold decline", () => {
    for (let rev = 150_000; rev <= 3_000_000; rev += 5_000) {
      for (const creditScore of [560, 600, 640, 680]) {
        for (const tib of [1, 2, 4]) {
          const r = preapprove({ annualRevenue: rev, creditScore, timeInBusinessYears: tib }, now);
          for (const [p, P] of [[r.termLoanMca, "tlmca"], [r.lineOfCreditRmca, "locr"]] as const) {
            const d = decide(rev, creditScore, tib)[P];
            if (p.decision === "declined" && d.reasons.some((x) => x.startsWith("Estimated lender approval"))) {
              expect(p.approvalProbability).toBeLessThan(MODEL.policy.approve_threshold[P]);
            }
          }
        }
      }
    }
  });
});

describe("POST /preapproval/sofi", () => {
  let server: Server;
  let base: string;
  const original = config.preapprovalApiKey;

  beforeAll(async () => {
    server = createServer().listen(0);
    await new Promise((r) => server.once("listening", r));
    base = `http://127.0.0.1:${(server.address() as AddressInfo).port}/preapproval/sofi`;
  });
  afterAll(async () => {
    config.preapprovalApiKey = original;
    await new Promise((r) => server.close(r));
  });

  const post = (body: string, key?: string) =>
    fetch(base, { method: "POST", headers: { "content-type": "application/json", ...(key ? { "x-api-key": key } : {}) }, body });
  const lead = JSON.stringify({ annualRevenue: 1_500_000, creditScore: 760, timeInBusinessYears: 8 });

  it("is disabled until an API key is configured", async () => {
    for (const key of ["", "   "]) {
      config.preapprovalApiKey = key;
      expect((await post(lead, "anything")).status).toBe(503);
    }
  });

  it("ignores whitespace around the configured key", async () => {
    config.preapprovalApiKey = "  test-key\n";
    expect((await post(lead, "test-key")).status).toBe(200);
  });

  it("requires the API key", async () => {
    config.preapprovalApiKey = "test-key";
    expect((await post(lead)).status).toBe(401);
    expect((await post(lead, "wrong-key")).status).toBe(401);
    const ok = await post(lead, "test-key");
    expect(ok.status).toBe(200);
    const body = (await ok.json()) as { termLoanMca: { decision: string }; modelVersion: string };
    expect(body.termLoanMca.decision).toBe("approved");
    expect(body.modelVersion).toBe(MODEL.model_version);
  });

  it("answers malformed and incomplete bodies with JSON 400s", async () => {
    config.preapprovalApiKey = "test-key";
    for (const body of ["{bad json", "5", "null", JSON.stringify({ annualRevenue: null, creditScore: 760, timeInBusinessYears: 8 }),
      JSON.stringify({ annualRevenue: 1_500_000, creditScore: 760, timeInBusinessYears: 2015 })]) {
      const res = await post(body, "test-key");
      expect(res.status).toBe(400);
      expect(res.headers.get("content-type")).toMatch(/application\/json/);
      expect(((await res.json()) as { error: string }).error).toBeTruthy();
    }
    const big = await post(JSON.stringify({ pad: "x".repeat(200_000) }), "test-key");
    expect(big.status).toBe(413);
    expect(big.headers.get("content-type")).toMatch(/application\/json/);
  });
});
