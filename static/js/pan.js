//ecouter button
document.addEventListener('DOMContentLoaded', function() {
    var addToCartBtn = document.getElementById('add-to-cart-btn');
    addToCartBtn.addEventListener('click', addToCart);
});

function addToCart() {
    // Logique pour ajouter le produit au panier
    alert('Produit ajouté au panier!');
}

var cart = [];

function addToCart() {
    var productId = 1; // ID du produit (peut être obtenu dynamiquement)
    var existingItem = cart.find(item => item.productId === productId);
    if (existingItem) {
        existingItem.quantity++;
    } else {
        cart.push({ productId: productId, quantity: 1 });
    }
    console.log(cart); // Affiche le panier dans la console
    alert('Produit ajouté au panier!');
}



// cart.js
document.addEventListener('DOMContentLoaded', function() {
    var cartItemsContainer = document.getElementById('cart-items');
    renderCartItems();

    function renderCartItems() {
        cartItemsContainer.innerHTML = '';
        cart.forEach(function(item) {
            var li = document.createElement('li');
            li.textContent = 'Produit ID: ' + item.productId + ', Quantité: ' + item.quantity;
            cartItemsContainer.appendChild(li);
        });
    }
});