import {register} from './models.mjs';

// Host command dispatch precedes skill dispatch in Command Code 1.66.0.
export default function (cmd) {
  register(cmd);
}
