// URL contenant les données JSON des articles
const url = 'http://localhost:8080/ApiBc/api/bc/GetItems'; // Remplacez cette URL par votre URL réelle

// Fonction pour récupérer les données JSON à partir de l'URL
async function recupererDonneesJSON() {
    try {
        const reponse = await fetch(url);
        if (!reponse.ok) {
            throw new Error('Erreur lors de la récupération des données JSON');
        }
        const data = await reponse.json();
        return data;
    } catch (erreur) {
        console.error('Une erreur s\'est produite:', erreur.message);
    }
}

// Fonction pour afficher les articles à partir des données JSON
async function afficherArticles() {
    const articles = await recupererDonneesJSON();
    const itemsContainer = document.getElementById('items-container');
    itemsContainer.innerHTML = '';

    articles.forEach(article => {
        const itemElement = document.createElement('div');
        itemElement.innerHTML = `
            <h3>${article.Description}</h3>
            <p>Prix: ${article.Description} $</p>
            <button onclick="ajouterAuPanier(${article.Description})">Ajouter au panier</button>
        `;
        itemsContainer.appendChild(itemElement);
    });
}
// Initialise l'affichage des articles
afficherArticles();