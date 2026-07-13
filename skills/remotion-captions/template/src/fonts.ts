import {loadFont as loadInter} from '@remotion/google-fonts/Inter';
import {loadFont as loadPlayfair} from '@remotion/google-fonts/PlayfairDisplay';

export const inter = loadInter('normal', {
  weights: ['700', '800', '900'],
  subsets: ['latin', 'latin-ext'],
});

// Contrast font for the keyword-highlight style.
export const playfair = loadPlayfair('italic', {
  weights: ['700', '800'],
  subsets: ['latin', 'latin-ext'],
});
