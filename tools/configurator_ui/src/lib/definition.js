import {setDefinition} from './engine.js';
export async function loadDefinition(client) {
  const definition = await client.getDefinition();
  setDefinition(definition);
  return definition;
}
