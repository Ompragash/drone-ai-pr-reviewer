# AI Code Reviewer - TODO & Improvements

## Current State

### File Statistics
- Total Lines of Code: 1,652
- Key Components:
  - `main.py`: 470 lines
  - `diff_parser.py`: 279 lines
  - `scm_client.py`: 275 lines
  - `plugin_config.py`: 214 lines
  - `llm_reviewer.py`: 208 lines

### Currently Supported Features
- ✅ Basic text file changes
- ✅ New file additions
- ✅ Multiple LLM providers via LiteLLM
- ✅ Basic file rename detection
- ✅ Mode change detection (skip-only)
- ✅ Multiple hunks in a file
- ✅ Configurable file filtering
- ✅ JSON-formatted review comments

## GitHub Actions AI Code Reviewer Comparison

### What They Do Better
1. **Code Suggestions**
   - Provides inline code suggestions
   - Uses GitHub's suggestion blocks
   - One-click apply suggestions
   - Context-aware fixes
   - Automated code improvements

2. **Diff Handling**
   - Binary file support
   - Complex rename detection
   - Special characters in filenames
   - Large diff pagination
   - Better line number mapping

2. **API Integration**
   - Uses GitHub GraphQL API
   - Native comment threading
   - Better review positioning
   - Access to PR metadata

3. **Code Efficiency**
   - Smaller codebase
   - Less boilerplate
   - Better use of platform APIs

## Improvement Plan

### Phase 1: Core Improvements
- [ ] Binary file detection and handling
- [ ] Proper handling of file renames with modifications
- [ ] Support for special characters in filenames
- [ ] Large diff pagination support
- [ ] Improve line number mapping accuracy

### Phase 2: Code Optimization
- [ ] Simplify diff parsing (evaluate alternatives)
- [ ] Reduce configuration complexity
- [ ] Streamline error handling
- [ ] Remove redundant logging
- [ ] Optimize type hints and documentation

### Phase 3: Feature Parity
- [ ] Add comment threading support
- [ ] Implement review batching
- [ ] Support file-level comments
- [ ] Add review summary generation
- [ ] Add code suggestions feature
  - [ ] Implement suggestion blocks
  - [ ] Add context-aware fixes
  - [ ] Support one-click apply via SCM API

### Phase 4: Advanced Features
- [ ] Add support for multiple SCM providers
- [ ] Implement caching for large diffs
- [ ] Add custom rules engine
- [ ] Support for code quality metrics
- [ ] Integration with existing linters

## Technical Debt
1. Manual diff parsing is complex and error-prone
2. Configuration handling is overly complex
3. Too much defensive programming
4. Limited use of SCM provider APIs
5. No test coverage metrics

## Next Steps
1. Implement binary file detection
2. Add proper diff pagination
3. Improve rename handling
4. Optimize core components
5. Add comprehensive testing
