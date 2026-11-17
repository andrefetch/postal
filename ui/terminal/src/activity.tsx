import {useEffect, useState} from 'react';
import {Text} from 'ink';

export const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
export const FRAME_INTERVAL = 80;

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
  const wave = (Math.cos((index - frame * 0.45) * Math.PI * 2 / Math.max(12, length + 6)) + 1) / 2;
  const shade = Math.round(16 + 239 * wave).toString(16).padStart(2, '0');
  return `#${shade.repeat(3)}`;
}

export function LoadingText({text, frame}: {text: string; frame: number}) {
  const characters = [...text];
  return <Text wrap="truncate"><Text color="#f3f3f3">{SPINNER_FRAMES[frame % SPINNER_FRAMES.length]} </Text>
    {characters.map((character, index) => <Text key={index} color={shimmerColor(index, frame, characters.length)}>{character}</Text>)}
  </Text>;
}
