//! SPDX expression grammar for package and upstream licence findings.

specmark::scope!("spec://org.vibevm.core/vibevm/modules/vibe-registry/PROP-023#maintainer-model");

/// SPDX expression grammar without legal interpretation or compatibility
/// judgement. Identifiers remain open-ended (as SPDX permits LicenseRef-*),
/// while prose and malformed boolean expressions are rejected.
pub(super) fn is_spdx_expression(value: &str) -> bool {
    if value.is_empty() || value.trim() != value || !value.is_ascii() {
        return false;
    }
    let tokens = tokenize_spdx(value);
    if tokens.is_empty() {
        return false;
    }
    let mut parser = SpdxParser { tokens, cursor: 0 };
    parser.expression() && parser.cursor == parser.tokens.len()
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SpdxToken<'a> {
    Identifier(&'a str),
    And,
    Or,
    With,
    Open,
    Close,
}

fn tokenize_spdx(value: &str) -> Vec<SpdxToken<'_>> {
    let mut tokens = Vec::new();
    let bytes = value.as_bytes();
    let mut cursor = 0;
    while cursor < bytes.len() {
        match bytes[cursor] {
            b' ' | b'\t' => cursor += 1,
            b'(' => {
                tokens.push(SpdxToken::Open);
                cursor += 1;
            }
            b')' => {
                tokens.push(SpdxToken::Close);
                cursor += 1;
            }
            _ => {
                let start = cursor;
                while cursor < bytes.len() && !matches!(bytes[cursor], b' ' | b'\t' | b'(' | b')') {
                    cursor += 1;
                }
                let word = &value[start..cursor];
                let token = match word {
                    "AND" => SpdxToken::And,
                    "OR" => SpdxToken::Or,
                    "WITH" => SpdxToken::With,
                    _ if valid_spdx_identifier(word) => SpdxToken::Identifier(word),
                    _ => return Vec::new(),
                };
                tokens.push(token);
            }
        }
    }
    tokens
}

fn valid_spdx_identifier(value: &str) -> bool {
    !value.is_empty()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'.' | b'+' | b':'))
}

struct SpdxParser<'a> {
    tokens: Vec<SpdxToken<'a>>,
    cursor: usize,
}

impl SpdxParser<'_> {
    fn expression(&mut self) -> bool {
        if !self.term() {
            return false;
        }
        while matches!(self.peek(), Some(SpdxToken::And | SpdxToken::Or)) {
            self.cursor += 1;
            if !self.term() {
                return false;
            }
        }
        true
    }

    fn term(&mut self) -> bool {
        match self.peek() {
            Some(SpdxToken::Identifier(_)) => self.cursor += 1,
            Some(SpdxToken::Open) => {
                self.cursor += 1;
                if !self.expression() || self.peek() != Some(SpdxToken::Close) {
                    return false;
                }
                self.cursor += 1;
            }
            _ => return false,
        }
        if self.peek() == Some(SpdxToken::With) {
            self.cursor += 1;
            if !matches!(self.peek(), Some(SpdxToken::Identifier(_))) {
                return false;
            }
            self.cursor += 1;
        }
        true
    }

    fn peek(&self) -> Option<SpdxToken<'_>> {
        self.tokens.get(self.cursor).copied()
    }
}
