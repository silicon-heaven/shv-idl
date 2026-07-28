import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';
import oxlint from 'eslint-plugin-oxlint';
import stylistic from '@stylistic/eslint-plugin';
import unicorn from 'eslint-plugin-unicorn';
import importX from 'eslint-plugin-import-x';
import pluginN from 'eslint-plugin-n';
import globals from 'globals';

export default tseslint.config(
    eslint.configs.recommended,
    ...tseslint.configs.recommended,
    ...tseslint.configs.stylistic,
    {
        plugins: {
            '@stylistic': stylistic,
            'unicorn': unicorn,
            'import-x': importX,
            'n': pluginN,
        },
        languageOptions: {
            globals: {
                ...globals.browser,
            },
            parserOptions: {
                projectService: true,
            },
        },
        rules: {
            '@stylistic/function-paren-newline': ['off'],
            '@stylistic/indent': ['error', 4],
            '@stylistic/indent-binary-ops': ['error', 4],
            '@stylistic/max-len': ['off'],
            '@stylistic/multiline-ternary': ['off'],
            '@stylistic/no-trailing-spaces': ['error'],
            '@stylistic/object-curly-newline': ['error', {
                ImportDeclaration: 'never',
            }],
            '@stylistic/operator-linebreak': ['off'],
            '@typescript-eslint/array-type': ['error', {
                default: 'array-simple',
            }],
            '@typescript-eslint/consistent-type-definitions': ['error', 'type'],
            '@typescript-eslint/no-misused-promises': ['error', {
                checksVoidReturn: false,
            }],
            '@typescript-eslint/naming-convention': ['error',
                {
                    selector: 'variableLike',
                    format: ['camelCase'],
                },
                {
                    selector: 'variableLike',
                    format: null,
                    modifiers: ['unused'],
                },
                {
                    format: ['camelCase', 'UPPER_CASE'],
                    selector: 'variable',
                    modifiers: ['const'],
                },
                {
                    format: ['PascalCase'],
                    selector: 'variable',
                    modifiers: ['const'],
                    filter: 'Validation$|Zod$',
                }],
            '@typescript-eslint/no-unsafe-assignment': ['off'],
            '@typescript-eslint/no-unsafe-call': ['off'],
            '@typescript-eslint/no-unsafe-enum-comparison': ['off'],
            '@typescript-eslint/strict-boolean-expressions': ['error', {
                allowString: false,
                allowNumber: false,
                allowNullableObject: false,
            }],
            '@typescript-eslint/switch-exhaustiveness-check': ['error', {
                considerDefaultExhaustiveForUnions: true,
            }],
            camelcase: ['off'],
            complexity: ['error', {
                variant: 'modified',
            }],
            '@typescript-eslint/strict-void-return': 'off',
            'capitalized-comments': ['error', 'always', {
                ignorePattern: 'oxlint',
                ignoreConsecutiveComments: true,
            }],
            'default-case': ['off'],
            'import-x/extensions': ['off'],
            'import-x/no-unassigned-import': ['off'],
            'n/prefer-global/process': ['off'],
            'n/prefer-global/url': ['off'],
            'no-await-in-loop': ['off'],
            'no-dupe-class-members': ['off'],
            'no-negated-condition': ['off'],
            'no-redeclare': ['off'],
            'no-unused-vars': ['off'],
            'no-void': ['error', {
                allowAsStatement: false,
            }],
            'no-warning-comments': ['off'],
            'unicorn/better-regex': ['error'],
            'unicorn/consistent-destructuring': ['error'],
            'unicorn/prefer-import-meta-properties': ['error'],
            'unicorn/consistent-function-scoping': ['off'],
            'unicorn/explicit-length-check': ['off'],
            'unicorn/filename-case': ['off'],
            'unicorn/no-negated-condition': ['off'],
            'unicorn/prefer-top-level-await': ['off'],
            'unicorn/prevent-abbreviations': ['off'],
            'unicorn/switch-case-braces': ['off'],
        },
    },
    ...oxlint.buildFromOxlintConfigFile('./.oxlintrc.json'),
);
