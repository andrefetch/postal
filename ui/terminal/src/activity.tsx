import {useEffect, useState} from 'react';
import {Text} from 'ink';

export const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
export const FRAME_INTERVAL = 40;

export function useActivityFrame(active: boolean) {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    if (!active) return;
    setFrame(0);
    const timer = setInterval(() => setFrame(current => current + 1), FRAME_INTERVAL);
    return () => clearInterval(timer);
  }, [active]);
  return frame;
}

export function shimmerColor(index: number, frame: number, length: number) {
  // A narrow dark band crosses white text each second, independent of its length.
  const spread = Math.max(1.5, length * 0.22);
  const progress = ((frame * FRAME_INTERVAL) % 1000) / 1000;
  const center = -spread + progress * (length - 1 + spread * 2);
  const distance = Math.min(1, Math.abs(index - center) / spread);
  const wave = (Math.cos(distance * Math.PI) + 1) / 2;
  const shade = Math.round(255 - 239 * wave).toString(16).padStart(2, '0');
  return `#${shade.repeat(3)}`;
}

export function LoadingText({text, frame}: {text: string; frame: number}) {
  const characters = [...text];
  return <Text wrap="truncate"><Text color="#f3f3f3">{SPINNER_FRAMES[frame % SPINNER_FRAMES.length]} </Text>
    {characters.map((character, index) => <Text key={index} color={shimmerColor(index, frame, characters.length)}>{character}</Text>)}
  </Text>;
}
