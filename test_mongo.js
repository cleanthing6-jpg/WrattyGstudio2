const { MongoClient } = require('mongodb');
const uri = 'mongodb+srv://wrattyg_db_user:Olokooyin1st@wrattygstudio2.qagy7ap.mongodb.net/?retryWrites=true&w=majority&appName=WrattyGstudio2&authSource=admin';
const client = new MongoClient(uri);

async function run() {
  try {
    await client.connect();
    console.log('✅ SUCCESS: Connected to MongoDB perfectly.');
    await client.db('wrattyg').command({ ping: 1 });
    console.log('✅ SUCCESS: Read access to wrattyg database confirmed.');
  } catch (e) {
    console.error('❌ FAILED:', e.message);
  } finally {
    await client.close();
  }
}
run();
