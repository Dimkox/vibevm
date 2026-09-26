/** @scope spec://org.vibevm.core/vibevm/common/PROP-057#SITE-ONE-SITE */

/**
 * Which VibeVM this is not, everywhere a crawler reads it.
 *
 * Search engines and model crawlers had been joining this project with
 * its namesakes — Phala Network's VibeVM, a development sandbox on Phala
 * Cloud; the tgbyte project of the same name; and, for the AI Native
 * Languages, the karanchawla VVM project (owner, 2026-09-26). The site
 * says so in four places, in the owner's own sentences: at the foot of
 * both landings, in the root `llms.txt` and `llms-full.txt`, and in the
 * structured data. A sentence that quietly went missing from one of them
 * would be the index's cue to join the two again, so each place is held
 * here.
 *
 * What is NOT here is anything about those projects. Each note names one
 * and says nothing further about it, and nothing on the site links to
 * one; the tests below check the words this site publishes, in the exact
 * form it publishes them.
 */

import { expect, test } from "@playwright/test";

import {
  AI_NATIVE_LANGUAGES_EN,
  AI_NATIVE_LANGUAGES_NOT_EN,
  AI_NATIVE_LANGUAGES_WHAT_EN,
  PHALA_DISAMBIGUATION_EN,
  STRINGS,
  TGBYTE_DISAMBIGUATION_EN,
} from "../src/landing/i18n.ts";

const LANDINGS = [
  { route: "/", locale: "en", says: "Phala Network's VibeVM" },
  { route: "/ru/", locale: "ru", says: "VibeVM от Phala Network" },
] as const;

for (const one of LANDINGS) {
  test(`${one.route} ends with the three notes, in the owner's order`, async ({
    page,
  }) => {
    await page.goto(one.route);
    const notes = page.locator("main .landing-disambiguation");
    await expect(notes).toHaveCount(3);

    const strings = STRINGS[one.locale];
    await expect(notes.nth(0)).toBeVisible();
    await expect(notes.nth(0)).toContainText(one.says);
    await expect(notes.nth(0)).toContainText("github.com/Phala-Network/VibeVM");
    await expect(notes.nth(0)).toContainText("Phala Cloud");

    /* The other two, word for word: they are the owner's sentences and
       the page is the place they are read, so nothing is matched loosely
       here. */
    await expect(notes.nth(1)).toHaveText(strings.disambiguationTgbyte);
    await expect(notes.nth(2)).toHaveText(strings.disambiguationAiNative);

    /* Last in the page's own content: small print after everything the
       page says, not a line inside it. */
    const last = page.locator("main > :last-child");
    await expect(last).toHaveClass(/\blanding-disambiguation\b/);
  });
}

/** The English wording is one string in one place; the page reads it. */
test("/ carries the two English notes exactly as they are written", async ({
  page,
}) => {
  await page.goto("/");
  const notes = page.locator("main .landing-disambiguation");
  await expect(notes.nth(1)).toHaveText(TGBYTE_DISAMBIGUATION_EN);
  await expect(notes.nth(2)).toHaveText(AI_NATIVE_LANGUAGES_EN);
});

test("the root llms.txt names each namesake, in order, before the index", async ({
  request,
}) => {
  const text = await (await request.get("/llms.txt")).text();
  const general = text.indexOf("Disambiguation:");
  const phala = text.indexOf(PHALA_DISAMBIGUATION_EN);
  const tgbyte = text.indexOf(TGBYTE_DISAMBIGUATION_EN);
  const aiNative = text.indexOf(AI_NATIVE_LANGUAGES_EN);
  expect(general).toBeGreaterThan(-1);
  expect(phala).toBeGreaterThan(general);
  expect(tgbyte).toBeGreaterThan(phala);
  expect(aiNative).toBeGreaterThan(tgbyte);
  expect(text.indexOf("## Project")).toBeGreaterThan(aiNative);
});

test("the root llms-full.txt says all three in its header", async ({
  request,
}) => {
  const text = await (await request.get("/llms-full.txt")).text();
  const header = text.slice(0, text.indexOf("\n---\n"));
  expect(header).toContain(PHALA_DISAMBIGUATION_EN);
  expect(header).toContain(TGBYTE_DISAMBIGUATION_EN);
  expect(header).toContain(AI_NATIVE_LANGUAGES_EN);
});

/** Every node of the site graph, whichever script it arrived in. */
function graphNodes(
  content: readonly string[],
): ReadonlyArray<Record<string, unknown>> {
  return content.flatMap((raw) => {
    const data = JSON.parse(raw) as { "@graph"?: Record<string, unknown>[] };
    return data["@graph"] ?? [];
  });
}

test("the structured data carries both application notes in one property", async ({
  page,
}) => {
  await page.goto("/");
  const nodes = graphNodes(
    await page.locator('script[type="application/ld+json"]').allTextContents(),
  );
  const software = nodes.find(
    (node) => node["@type"] === "SoftwareApplication",
  );
  expect(software?.["disambiguatingDescription"]).toBe(
    `${PHALA_DISAMBIGUATION_EN} ${TGBYTE_DISAMBIGUATION_EN}`,
  );
});

/**
 * And the languages as an entity of their own: what they are in
 * `description`, which project they are not in the property schema.org
 * keeps for that, and the page on this domain that argues for them.
 */
test("the structured data carries the languages as their own entity", async ({
  page,
}) => {
  await page.goto("/");
  const nodes = graphNodes(
    await page.locator('script[type="application/ld+json"]').allTextContents(),
  );
  const language = nodes.find((node) => node["@type"] === "ComputerLanguage");
  expect(language?.["name"]).toBe("AI Native Languages");
  expect(language?.["alternateName"]).toEqual([
    "AI Native Rust",
    "AI-Native Rust",
  ]);
  expect(language?.["url"]).toBe("https://vibevm.org/why/ai-native/");
  expect(language?.["description"]).toBe(AI_NATIVE_LANGUAGES_WHAT_EN);
  expect(language?.["disambiguatingDescription"]).toBe(
    AI_NATIVE_LANGUAGES_NOT_EN,
  );
});

/**
 * A namesake is named and never described, and never linked to.
 *
 * The rule the owner set: the words appear inside these sentences and
 * nowhere else, and no link on the page leads to either project. A link
 * would be this site recommending what it has just said it is not.
 */
for (const one of LANDINGS) {
  test(`${one.route} names the namesakes only in the small print`, async ({
    page,
  }) => {
    await page.goto(one.route);
    const outside = await page.evaluate(() => {
      const notes = [...document.querySelectorAll(".landing-disambiguation")];
      const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
      );
      const found: string[] = [];
      for (
        let node = walker.nextNode();
        node !== null;
        node = walker.nextNode()
      ) {
        const text = node.textContent ?? "";
        if (!/karanchawla|tgbyte/i.test(text)) continue;
        if (notes.some((note) => note.contains(node))) continue;
        /* What a reader READS, so the machine surfaces are passed over:
           the head's structured data says the same sentences on purpose,
           and the framework's serialised state carries a copy of them. */
        const owner = node.parentElement;
        if (owner === null) continue;
        if (owner.closest("script, style, template, pre, code") !== null) {
          continue;
        }
        found.push(text.trim());
      }
      return found;
    });
    expect(outside).toEqual([]);

    const hrefs = await page
      .locator("a[href]")
      .evaluateAll((links) =>
        links.map((link) => link.getAttribute("href") ?? ""),
      );
    expect(hrefs.filter((at) => /karanchawla|tgbyte/i.test(at))).toEqual([]);
  });
}
