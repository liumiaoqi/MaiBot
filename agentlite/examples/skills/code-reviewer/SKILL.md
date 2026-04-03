---
name: code-reviewer
description: Review code for bugs, style issues, security vulnerabilities, and best practices. Use when the user asks to review, check, or audit code.
type: standard
---

# Code Reviewer

A comprehensive code review skill that checks for common issues and provides actionable feedback.

## Review Checklist

### 1. Correctness
- Check for logical errors
- Verify edge cases are handled
- Look for off-by-one errors
- Check null/None handling
- Verify error handling paths

### 2. Style & Readability
- Naming conventions (clear, descriptive names)
- Code organization and structure
- Comments where needed (not obvious code)
- Consistent formatting
- Function/class length

### 3. Performance
- Inefficient algorithms (O(n²) when O(n) possible)
- Unnecessary object creation
- Memory leaks
- Redundant operations

### 4. Security
- SQL injection vulnerabilities
- XSS vulnerabilities (for web code)
- Hardcoded secrets/passwords
- Unsafe deserialization
- Path traversal risks

### 5. Best Practices
- DRY principle (Don't Repeat Yourself)
- SOLID principles
- Proper use of language features
- Test coverage considerations

## Output Format

Provide your review in this structure:

```
## Summary
Brief overall assessment

## Critical Issues
- Issue 1: Description and fix
- Issue 2: Description and fix

## Warnings
- Warning 1: Description and suggestion

## Suggestions
- Suggestion 1: How to improve

## Positive Notes
- What's done well
```

Be constructive and specific. Include code examples for suggested fixes.
