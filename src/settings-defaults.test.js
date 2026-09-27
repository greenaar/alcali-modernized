/* eslint-env jest */
import defaultSettings, { mergeSettings } from "./settings-defaults"

const pages = Object.keys(defaultSettings().UserSettings.refresh_on_load)

test("every page refreshes on load by default", () => {
  const merged = mergeSettings(defaultSettings(), {})
  pages.forEach(page => expect(merged.UserSettings.refresh_on_load[page]).toBe(true))
})

test("a per-page choice survives the merge", () => {
  const merged = mergeSettings(defaultSettings(), {
    UserSettings: { refresh_on_load: { Minions: false } },
  })
  expect(merged.UserSettings.refresh_on_load.Minions).toBe(false)
  expect(merged.UserSettings.refresh_on_load.Keys).toBe(true)
})

test.each([true, false])("3008.13.0's single switch (%s) carries to every page", value => {
  const merged = mergeSettings(defaultSettings(), {
    UserSettings: { refresh_on_load: value, max_notifs: 3 },
  })
  pages.forEach(page => expect(merged.UserSettings.refresh_on_load[page]).toBe(value))
  expect(merged.UserSettings.max_notifs).toBe(3)
})
