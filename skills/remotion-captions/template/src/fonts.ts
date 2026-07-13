// Bundled fonts (@fontsource) — no network needed at render time, which
// matters in sandboxed/proxied environments where headless Chrome can't
// reach Google Fonts.
import '@fontsource/inter/700.css';
import '@fontsource/inter/800.css';
import '@fontsource/inter/900.css';
import '@fontsource/playfair-display/700-italic.css';
import '@fontsource/playfair-display/800-italic.css';

export const inter = {fontFamily: 'Inter'};

// Contrast font for the keyword-highlight style.
export const playfair = {fontFamily: '"Playfair Display"'};
