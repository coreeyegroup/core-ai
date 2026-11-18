import {createRoot} from 'react-dom/client';
import App from './App';
import './style.css';
import './themes.css';
import './chat.css';
import 'katex/dist/katex.min.css';
createRoot(document.getElementById('root')!).render(<App/>);
