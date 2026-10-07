const fs = require('fs');
const path = require('path');

// 1. Get the date for the most recent information on Smogon
const today = new Date();
let year = today.getFullYear();
let month;
// 2. Always go backwards 1 month,
//  If it is January set the month to December in the string format, getMonth() gives a range of 0-11
if (today.getMonth() === 0) {
    year -= 1;
    month = "12";
} else {
    month = String(today.getMonth()).padStart(2, '0');
}
// 3. Set the current format
const POKEMON_GENERATION = 'gen9';
const POKEMON_REGULATION = 'ma';

// 4. Get the url and save it locally in champions-vgc-stats.json
const URL = `https://smogon.com/stats/${year}-${month}/chaos/${POKEMON_GENERATION}championsvgc${year}reg${POKEMON_REGULATION}-1630.json`;
const OUTPUT_PATH = path.join(__dirname, 'champions-vgc-stats.json');

// --- DATA CLEANING HELPER FUNCTIONS ---

// Helper function to sort object properties by value (highest first) and slice the top elements
function processTopData(dataObject, limit = null) {
    if (!dataObject) return {};
    
    // Object.entries creates [key, value] pairs. We sort by value (index 1).
    const sortedArray = Object.entries(dataObject)
        .sort((a, b) => b[1] - a[1]); 
        
    const slicedArray = limit ? sortedArray.slice(0, limit) : sortedArray;
    
    return Object.fromEntries(slicedArray);
}

// Main clean-up framework for the raw Smogon payload
function cleanPokemonJson(rawChaosData) {
    const cleaned = {
        info: rawChaosData.info, // Keep global file metadata
        pokemon: {}
    };

    for (const [pokemonName, stats] of Object.entries(rawChaosData.data)) {

        cleaned.pokemon[pokemonName] = { ...stats };

        cleaned.pokemon[pokemonName]["Abilities"] = processTopData(stats["Abilities"]);
        cleaned.pokemon[pokemonName]["Items"] = processTopData(stats["Items"], 5);
        cleaned.pokemon[pokemonName]["Spreads"] = processTopData(stats["Spreads"], 15);
        cleaned.pokemon[pokemonName]["Moves"] = processTopData(stats["Moves"], 10);
        cleaned.pokemon[pokemonName]["Teammates"] = processTopData(stats["Teammates"], 10);
    }
    return cleaned;
}

// 5. Fetch the data
async function downloadSmogonData() {
    try {
        console.log(`Checking layout for ${year}-${month}...`);
        console.log(`Fetching VGC data from: ${URL}`);
        
        const response = await fetch(URL);
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status} (Stats for ${year}-${month} might not be uploaded yet)`);
        }
        
        const rawData = await response.json();
        console.log("Cleaning and reducing data complexity...");
        
        // Process the raw data through the cleaning pipeline
        const cleanedData = cleanPokemonJson(rawData);
        
        // Save the optimized structure instead
        fs.writeFileSync(OUTPUT_PATH, JSON.stringify(cleanedData, null, 2), 'utf8');
        console.log(`Success! Saved to ${OUTPUT_PATH}`);
    } catch (error) {
        console.error('Error fetching Smogon data:', error.message);
    }
}

downloadSmogonData();