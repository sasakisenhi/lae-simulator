While looking into #1938, I added `fixTypes` to my VS Code settings.json:

```
  "eslint.options": {
    "fixTypes": ["problem", "suggestion", "layout"]
  },
```

However, I realized that that broke the ability to apply auto fixes within VS Code for my [eslint-plugin-header](https://github.com/Stuk/eslint-plugin-header) rules.

It appears that this is because eslint-plugin-header's `meta` doesn't specify a `docs.url`, and vscode-eslint only stores rule information for rules that have `docs.url`:

https://github.com/microsoft/vscode-eslint/blob/release/3.0.10/server/src/eslint.ts#L162

Is this behavior necessary / correct?
