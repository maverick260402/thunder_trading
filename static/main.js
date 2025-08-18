// Main JavaScript file for Thunder Trading Application
// Contains all functionality including proper trading status management

// Variables for storing selected stock information
let selectedStockToken = null;
let selectedTradingSymbol = null;
let selectedSymbolToken = null;

// Variables for Supertrend parameters
let supertrendLength = 10; // Default value
let supertrendFactor = 2.0;  // Default value

// Trading status
let isTradingActive = false;

// Initialize data
let data = [];

// Function to load JSON data
async function loadJsonData() {
    try {
        // Fetch data from our backend endpoint
        const response = await fetch('/get_stock_data');
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Failed to load stock data: ${response.status} ${response.statusText}`);
        }
        
        const loadedData = await response.json();
        if (!Array.isArray(loadedData) || loadedData.length === 0) {
            throw new Error('Invalid data format received from server');
        }
        
        console.log(`Loaded ${loadedData.length} stock records successfully`);
        
        // Set the global data variable
        data = loadedData;
        
        // Check if there's a pending trading status update
        if (window.pendingTradingStatus) {
            console.log('Applying pending trading status update');
            updateUIWithActiveTrading(window.pendingTradingStatus);
            window.pendingTradingStatus = null; // Clear the pending status
        }
        
        return loadedData;
    } catch (error) {
        console.error('Error loading stock data:', error);
        
        // Show error message to user
        const errorMessage = document.createElement('div');
        errorMessage.style.color = 'red';
        errorMessage.style.padding = '10px';
        errorMessage.style.margin = '10px';
        errorMessage.style.border = '1px solid red';
        errorMessage.style.borderRadius = '4px';
        errorMessage.innerHTML = `
            <strong>Error loading stock data:</strong><br>
            ${error.message}<br>
            Please try the following:<br>
            1. Check your internet connection<br>
            2. Refresh the page<br>
            3. If the problem persists, contact support
        `;
        
        // Insert the error message at the top of the page
        const container = document.getElementById('dashboardContainer') || document.body;
        container.insertBefore(errorMessage, container.firstChild);
        
        // Return empty array to prevent app from completely failing
        return [];
    }
}

// Function to search for stock details
function searchStock() {
    const searchInput = document.getElementById('stockSearch').value.trim();
    const instrumentType = document.getElementById('instrumentType').value;

    // Extract the stock name and symbol from the input
    const [stockName, stockSymbol] = extractNameAndSymbol(searchInput);

    if (!stockName && !stockSymbol) {
        alert("Please enter a stock name or symbol.");
        return;
    }

    const results = {
        EQ: [],
        FUT: [],
        OPT: [],
        Others: []
    };

    data.forEach(instrument => {
        const matchesName = stockName ? instrument.name?.toUpperCase().includes(stockName.toUpperCase()) : true;
        const matchesSymbol = stockSymbol ? instrument.symbol?.toUpperCase().includes(stockSymbol.toUpperCase()) : true;

        if (matchesName && matchesSymbol) {
            if (instrumentType === "") {
                if (instrument.symbol?.includes('-EQ')) {
                    results.EQ.push({ name: instrument.name, symbol: instrument.symbol, token: instrument.token });
                } else if (instrument.symbol?.includes('FUT')) {
                    results.FUT.push({ name: instrument.name, symbol: instrument.symbol, token: instrument.token });
                } else if (instrument.symbol?.endsWith('PE') || instrument.symbol?.endsWith('CE')) {
                    results.OPT.push({ name: instrument.name, symbol: instrument.symbol, token: instrument.token });
                } else {
                    results.Others.push({ name: instrument.name, symbol: instrument.symbol, token: instrument.token });
                }
            } else if (instrumentType === "EQ" && instrument.symbol?.includes('-EQ')) {
                results.EQ.push({ name: instrument.name, symbol: instrument.symbol, token: instrument.token });
            } else if (instrumentType === "FUT" && instrument.symbol?.includes('FUT')) {
                results.FUT.push({ name: instrument.name, symbol: instrument.symbol, token: instrument.token });
            } else if (instrumentType === "OPT" && (instrument.symbol?.endsWith('PE') || instrument.symbol?.endsWith('CE'))) {
                results.OPT.push({ name: instrument.name, symbol: instrument.symbol, token: instrument.token });
            }
        }
    });

    const resultLabel = document.getElementById('resultLabel');
    resultLabel.innerHTML = '';

    const displayResults = (type, header) => {
        if (results[type].length > 0) {
            const typeHeader = document.createElement('h3');
            typeHeader.textContent = header;
            resultLabel.appendChild(typeHeader);
            results[type].forEach(stock => {
                const resultItem = document.createElement('div');
                resultItem.textContent = `Name: ${stock.name}, Symbol: ${stock.symbol}, Token: ${stock.token}`;
                resultItem.style.cursor = 'pointer';
                resultItem.classList.add('search-result-item');
                resultItem.addEventListener('click', () => {
                    // Update the search bar with the selected stock's name and symbol
                    document.getElementById('stockSearch').value = `${stock.name} (${stock.symbol})`;
                    // Store the trading symbol and token
                    selectedTradingSymbol = stock.symbol;
                    selectedSymbolToken = stock.token;
                    
                    // Display the stock name and symbol
                    displaySelectedStock(stock.name, stock.symbol);
                    
                    // Enable the order form
                    enableOrderForm();
                    
                    console.log('Selected Stock:', {
                        name: stock.name,
                        symbol: selectedTradingSymbol,
                        token: selectedSymbolToken
                    });
                });
                resultLabel.appendChild(resultItem);
            });
        }
    };

    if (instrumentType === "") {
        displayResults('EQ', 'Equities');
        displayResults('FUT', 'Futures');
        displayResults('OPT', 'Options');
        displayResults('Others', 'Others');
    } else if (instrumentType === "EQ") {
        displayResults('EQ', 'Equities');
    } else if (instrumentType === "FUT") {
        displayResults('FUT', 'Futures');
    } else if (instrumentType === "OPT") {
        displayResults('OPT', 'Options');
    }

    if (results.EQ.length === 0 && results.FUT.length === 0 && results.OPT.length === 0 && results.Others.length === 0) {
        resultLabel.textContent = "No results found.";
    }
}

// Function to extract name and symbol from the input
function extractNameAndSymbol(input) {
    const match = input.match(/^(.*?)\s*\((.*?)\)$/); // Match "Name (Symbol)"
    if (match) {
        return [match[1].trim(), match[2].trim()]; // Return [name, symbol]
    }
    return [input.trim(), null]; // Return [name, null] if no symbol is found
}

// Function to display the selected stock
function displaySelectedStock(name, symbol) {
    const resultLabel = document.getElementById('resultLabel');
    resultLabel.innerHTML = `
        <div class="selected-stock">
            <h3>Selected Stock</h3>
            <p><strong>Name:</strong> ${name}</p>
            <p><strong>Symbol:</strong> ${symbol}</p>
        </div>
    `;
}

// Function to update suggestions
function updateSuggestions() {
    const searchInput = document.getElementById('stockSearch').value.trim();
    const instrumentType = document.getElementById('instrumentType').value;
    const datalist = document.getElementById('stockSuggestions');
    
    // Clear existing options
    datalist.innerHTML = '';
    
    // Exit if search input is too short
    if (searchInput.length < 2) return;
    
    // Extract name part from search input
    const searchTerm = searchInput.split('(')[0].trim().toUpperCase();
    
    // Find matching stocks
    const matches = data.filter(instrument => {
        // Check if name or symbol matches
        const nameMatches = instrument.name && instrument.name.toUpperCase().includes(searchTerm);
        const symbolMatches = instrument.symbol && instrument.symbol.toUpperCase().includes(searchTerm);
        
        // Apply instrument type filter if selected
        if (instrumentType === "EQ") {
            return (nameMatches || symbolMatches) && instrument.symbol && instrument.symbol.includes('-EQ');
        } else if (instrumentType === "FUT") {
            return (nameMatches || symbolMatches) && instrument.symbol && instrument.symbol.includes('FUT');
        } else if (instrumentType === "OPT") {
            return (nameMatches || symbolMatches) && 
                   instrument.symbol && 
                   (instrument.symbol.endsWith('PE') || instrument.symbol.endsWith('CE'));
        } else {
            return nameMatches || symbolMatches;
        }
    });
    
    // Limit to 10 suggestions for performance
    const limitedMatches = matches.slice(0, 10);
    
    // Add matching options to datalist
    limitedMatches.forEach(stock => {
        const option = document.createElement('option');
        option.value = `${stock.name} (${stock.symbol})`;
        datalist.appendChild(option);
    });
}

// Function to toggle password visibility
function togglePasswordVisibility(inputId, buttonId) {
    const input = document.getElementById(inputId);
    const button = document.getElementById(buttonId);
    const showText = button.querySelector('.show-text');
    const hideText = button.querySelector('.hide-text');
    
    if (input.type === 'password') {
        input.type = 'text';
        showText.style.display = 'none';
        hideText.style.display = 'inline';
    } else {
        input.type = 'password';
        showText.style.display = 'inline';
        hideText.style.display = 'none';
    }
}

// Function to save API token
function saveApiToken() {
    const apiToken = document.getElementById('apiToken').value.trim();
    if (!apiToken) {
        showApiStatus('error', 'Please enter an API token');
        return;
    }
    
    // Validate token format (basic validation)
    if (apiToken.length < 8) {
        showApiStatus('error', 'API token appears too short. Please check and try again.');
        return;
    }
    
    // Store in localStorage
    localStorage.setItem('tradingBot_apiToken', apiToken);
    showApiStatus('success', 'API token saved and validated successfully');
    // Call the API to validate token
    //validateApiToken(apiToken);
}

// Function to validate API token with the server
async function validateApiToken(apiToken) {
    try {
        const response = await fetch('/validate_token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ api_token: apiToken })
        });
        
        const result = await response.json();
        console.log('Token validation result:', result);
        
        if (response.ok) {
            showApiStatus('success', 'API token saved and validated successfully');
            
            // After successful token validation, check trading status
            console.log('API token validated, now checking trading status...');
            await checkTradingStatus();
        } else {
            showApiStatus('error', result.error || 'Failed to validate API token');
        }
    } catch (error) {
        console.error('Error validating API token:', error);
        showApiStatus('error', 'Error validating API token: ' + error.message);
    }
}

// Function to refresh API token 
async function refreshApiToken() {
    const apiToken = localStorage.getItem('tradingBot_apiToken');
    if (!apiToken) {
        showApiStatus('error', 'No API token found to refresh');
        return;
    }
    
    try {
        const response = await fetch('/refresh_token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ api_token: apiToken })
        });
        
        const result = await response.json();
        console.log('Token refresh result:', result);
        
        if (response.ok) {
            // Update the stored token with the new one
            localStorage.setItem('tradingBot_apiToken', result.new_token);
            document.getElementById('apiToken').value = result.new_token;
            showApiStatus('success', 'API token refreshed successfully');
        } else {
            showApiStatus('error', result.error || 'Failed to refresh API token');
        }
    } catch (error) {
        console.error('Error refreshing API token:', error);
        showApiStatus('error', 'Error refreshing API token: ' + error.message);
    }
}

// Function to show API status message
function showApiStatus(type, message) {
    const statusContainer = document.getElementById('apiStatus');
    if (!statusContainer) return;
    
    statusContainer.textContent = message;
    statusContainer.className = 'api-status';
    
    if (type === 'success') {
        statusContainer.classList.add('success');
    } else if (type === 'error') {
        statusContainer.classList.add('error');
    }
    
    // Clear status after 5 seconds
    setTimeout(() => {
        statusContainer.textContent = '';
        statusContainer.className = 'api-status';
    }, 5000);
}

// Function to load saved API token on page load
function loadSavedApiToken() {
    const apiToken = localStorage.getItem('tradingBot_apiToken');
    if (apiToken) {
        document.getElementById('apiToken').value = apiToken;
        console.log('Loaded saved API token');
    }
}

// New function to update UI when trading is active
function updateUIWithActiveTrading(statusData) {
    // Try to find the stock name from loaded data
    const stockInfo = data.find(instrument => 
        instrument && instrument.symbol === statusData.symbol
    );
    
    if (stockInfo) {
        displaySelectedStock(stockInfo.name, stockInfo.symbol);
        // Update the search input
        document.getElementById('stockSearch').value = `${stockInfo.name} (${stockInfo.symbol})`;
    } else {
        displaySelectedStock("Selected Stock", statusData.symbol);
        // Update the search input with just the symbol
        document.getElementById('stockSearch').value = statusData.symbol;
    }
    
    // Update quantity field if available
    if (statusData.quantity) {
        const quantityInput = document.getElementById('quantity');
        if (quantityInput) {
            quantityInput.value = statusData.quantity;
        }
    }
    
    // Update candle duration if available
    if (statusData.candle_duration) {
        const candleDurationSelect = document.getElementById('candleDuration');
        if (candleDurationSelect) {
            candleDurationSelect.value = statusData.candle_duration;
        }
    }
    
    // Enable the order form
    enableOrderForm();
    
    console.log('UI updated with active trading status');
}

// FIXED: Check trading status without requiring API token first
async function checkTradingStatus() {
    try {
        console.log('Checking trading status...');
        
        // First, try to check trading status WITHOUT requiring API token
        // This is a public endpoint that just checks if trading is active
        const response = await fetch('/trading_status', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const statusData = await response.json();
        console.log('Trading status response:', statusData);
        
        if (response.ok) {
            isTradingActive = statusData.active;
            
            if (isTradingActive) {
                console.log('Trading is active for symbol:', statusData.symbol);
                
                // Update global variables
                if (statusData.symbol) {
                    selectedTradingSymbol = statusData.symbol;
                    selectedSymbolToken = statusData.token;
                    
                    // Wait for data to be loaded before trying to find stock info
                    if (data && data.length > 0) {
                        updateUIWithActiveTrading(statusData);
                    } else {
                        // Store the status data to update UI later when data is loaded
                        window.pendingTradingStatus = statusData;
                        console.log('Data not loaded yet, storing trading status for later update');
                    }
                }
                
                updateTradingButtonState();
                
                // Show a message to user that trading is active but API token is needed to stop it
                const apiToken = localStorage.getItem('tradingBot_apiToken');
                if (!apiToken) {
                    showApiStatus('warning', 'Trading is currently active. Please enter your API token to manage it.');
                }
                
            } else {
                console.log('No active trading detected');
                updateTradingButtonState();
            }
        } else {
            console.error('Failed to check trading status:', statusData);
            // If the endpoint requires authentication, we'll handle it gracefully
            if (response.status === 401) {
                console.log('Trading status check requires API token');
                updateTradingButtonState(); // Update UI to show inactive state
            }
        }
    } catch (error) {
        console.error('Error checking trading status:', error);
        // Don't fail silently - still update the UI
        updateTradingButtonState();
    }
}

// Function to update trading button state
function updateTradingButtonState() {
    const orderForm = document.getElementById('orderForm');
    if (!orderForm) return;
    
    const orderButton = orderForm.querySelector('.order-button');
    if (!orderButton) return;
    
    if (isTradingActive) {
        orderButton.textContent = 'Stop Trading';
        orderButton.classList.add('stop-button');
        
        // Update trading status indicator
        const tradingStatus = document.getElementById('tradingStatus');
        if (tradingStatus) {
            tradingStatus.classList.remove('inactive');
            tradingStatus.classList.add('active');
            tradingStatus.textContent = 'Trading is currently ACTIVE';
        }
    } else {
        orderButton.textContent = 'Start Trading';
        orderButton.classList.remove('stop-button');
        
        // Update trading status indicator
        const tradingStatus = document.getElementById('tradingStatus');
        if (tradingStatus) {
            tradingStatus.classList.remove('active');
            tradingStatus.classList.add('inactive');
            tradingStatus.textContent = 'Trading is currently inactive';
        }
    }
}

// Function to enable/disable order form
function enableOrderForm() {
    const orderForm = document.getElementById('orderForm');
    if (!orderForm) return;
    
    const orderButton = orderForm.querySelector('.order-button');
    if (!orderButton) return;
    
    if (selectedTradingSymbol && selectedSymbolToken) {
        orderButton.disabled = false;
        console.log('Order form enabled for:', selectedTradingSymbol);
    } else {
        orderButton.disabled = true;
        console.log('Order form disabled - no stock selected');
    }
    
    // Update button state
    updateTradingButtonState();
}

// Function to handle order submission
async function handleOrderSubmit(event) {
    event.preventDefault();
    
    if (isTradingActive) {
        // If trading is active, stop it
        await stopTrading();
    } else {
        // If trading is not active, start it
        await startTrading();
    }
}

// Function to start trading
async function startTrading() {
    console.log('Start trading attempted with:', {
        symbol: selectedTradingSymbol,
        token: selectedSymbolToken
    });
    
    if (!selectedTradingSymbol || !selectedSymbolToken) {
        alert('Please select a stock first');
        return;
    }

    // Get API token for the request
    const apiToken = localStorage.getItem('tradingBot_apiToken');
    if (!apiToken) {
        alert('API Token is required. Please save your API Token first.');
        return;
    }

    // Find the selected stock's details from the JSON data
    const selectedStock = data.find(stock => stock.token === selectedSymbolToken);
    if (!selectedStock || !selectedStock.exch_seg) {
        alert('Stock details not found for the selected stock.');
        return;
    }

    const orderData = {
        tradingsymbol: selectedTradingSymbol,
        symboltoken: selectedSymbolToken,   
        exchange: selectedStock.exch_seg,
        name: selectedStock.name,
        quantity: document.getElementById('quantity').value,
        candle_duration: document.getElementById('candleDuration').value,
        api_token: "Naughty Boy not for you.",
        instrument_type: selectedStock.instrumenttype,
        // Add Supertrend parameters to the request
        supertrend_length: supertrendLength,
        supertrend_factor: supertrendFactor
    };

    console.log('Submitting order with data:', orderData);

    try {
        const response = await fetch('/apply_supertrend', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': `Bearer ABCDEFG`
            },
            body: JSON.stringify(orderData)
        });

        const result = await response.json();
        console.log('Server response:', result);
        
        if (response.ok) {
            alert('Supertrend strategy started successfully!');
            isTradingActive = true;
            updateTradingButtonState();
            
            // Update trading history display
            const historyContainer = document.getElementById('historyContainer');
            if (historyContainer) {
                const timestamp = new Date().toLocaleString();
                const candleDuration = document.getElementById('candleDuration').value;
                historyContainer.innerHTML = `<div class="history-entry">
                    <p><strong>Strategy started:</strong> ${timestamp}</p>
                    <p><strong>Name:</strong> ${selectedStock.name}</p>
                    <p><strong>Symbol:</strong> ${selectedTradingSymbol}</p>
                    <p><strong>Quantity:</strong> ${document.getElementById('quantity').value}</p>
                    <p><strong>Candle Duration:</strong> ${candleDuration} Minute${candleDuration === '1' ? '' : 's'}</p>
                    <p><strong>Supertrend Length:</strong> ${supertrendLength}</p>
                    <p><strong>Supertrend Factor:</strong> ${supertrendFactor}</p>
                </div>` + historyContainer.innerHTML;
            }
        } else {
            alert('Failed to start strategy: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error starting strategy:', error);
        alert('Error starting strategy: ' + error.message);
    }
}
// Function to stop trading
async function stopTrading() {
    const apiToken = localStorage.getItem('tradingBot_apiToken');
    if (!apiToken) {
        alert('API Token is required to stop trading');
        return;
    }

    try {
        const response = await fetch('/stop_supertrend', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ABCDEFG`
            },
            //body: JSON.stringify({ api_token: apiToken })
        });

        const result = await response.json();
        console.log('Stop trading response:', result);
        
        if (response.ok) {
            alert('Trading stopped successfully');
            isTradingActive = false;
            updateTradingButtonState();
            
            // Update trading history display
            const historyContainer = document.getElementById('historyContainer');
            if (historyContainer) {
                const timestamp = new Date().toLocaleString();
                historyContainer.innerHTML = `<div class="history-entry">
                    <p><strong>Strategy stopped:</strong> ${timestamp}</p>
                </div>` + historyContainer.innerHTML;
            }
        } else {
            alert('Failed to stop trading: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error stopping trading:', error);
        alert('Error stopping trading: ' + error.message);
    }
}

// Function to handle Supertrend calculation
function handleSupertrendCalculation() {
    const lengthInput = document.getElementById('stLength');
    const factorInput = document.getElementById('stFactor');
    
    // Get and validate the input values
    const length = parseInt(lengthInput.value);
    const factor = parseFloat(factorInput.value);
    
    if (isNaN(length) || length <= 0) {
        alert('Please enter a valid length (positive number)');
        return;
    }
    
    if (isNaN(factor) || factor <= 0) {
        alert('Please enter a valid factor (positive number)');
        return;
    }
    
    supertrendLength = length;
    supertrendFactor = factor;
    
    // Display a message indicating the parameter changes
    const supertrendDisplay = document.getElementById('supertrendDisplay');
    if (supertrendDisplay) {
        supertrendDisplay.innerHTML = `
            <p>Supertrend parameters updated:</p>
            <ul>
                <li>Length: ${length}</li>
                <li>Factor: ${factor}</li>
            </ul>
            <p>These parameters will be used when you start trading.</p>
        `;
    }
}

// Function to handle stock selection
function handleStockSelection() {
    const searchInput = document.getElementById('stockSearch').value.trim();
    if (!searchInput.includes('(') || !searchInput.includes(')')) return;
    
    // Extract stock info from the search input
    const match = searchInput.match(/^(.*?)\s*\((.*?)\)$/);
    if (!match) return;
    
    const stockName = match[1].trim();
    const stockSymbol = match[2].trim();
    
    // Find the stock token
    const stock = data.find(item => 
        item.symbol === stockSymbol && 
        item.name === stockName
    );
    
    if (stock) {
        selectedTradingSymbol = stock.symbol;
        selectedSymbolToken = stock.token;
        
        displaySelectedStock(stock.name, stock.symbol);
        enableOrderForm();
        
        console.log('Selected Stock:', {
            name: stock.name,
            symbol: selectedTradingSymbol,
            token: selectedSymbolToken
        });
    }
}

// Modified DOMContentLoaded event listener with proper sequencing
document.addEventListener('DOMContentLoaded', async function() {
    // Login form submission event listener
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', async function(event) {
            event.preventDefault();
            const username = document.getElementById('loginId').value;
            const password = document.getElementById('password').value;

            // Send login request to backend
            try {
                const response = await fetch('/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ username, password })
                });
                
                const loginData = await response.json();
                
                if (loginData.token) {
                    // Hide login container, show dashboard
                    document.getElementById('loginContainer').style.display = 'none';
                    document.getElementById('dashboardContainer').style.display = 'block';
                    
                    // Load saved API token
                    loadSavedApiToken();
                    
                    // IMPORTANT: Proper sequencing - load data first, then check status
                    console.log('Login successful, loading data and checking trading status...');
                    
                    try {
                        //First Check Trading Status
                        // Then check trading status (this will work even without API token)
                        await checkTradingStatus();
                        
                        // Initialize button state
                        updateTradingButtonState();

                         // Load stock data afterchecking trading status
                        const loadedData = await loadJsonData();
                        console.log('Stock data loaded, now checking trading status...');
                        
                        
                    } catch (error) {
                        console.error('Error during post-login initialization:', error);
                    }
                    
                } else {
                    alert('Login failed: ' + (loginData.message || 'Unknown error'));
                }
            } catch (error) {
                console.error('Login error:', error);
                alert('Login failed: ' + error.message);
            }
        });
    }
    
    // Search button event listener
    const searchButton = document.getElementById('searchButton');
    if (searchButton) {
        searchButton.addEventListener('click', searchStock);
    }
    
    // Stock search input event listener
    const stockSearch = document.getElementById('stockSearch');
    if (stockSearch) {
        stockSearch.addEventListener('input', updateSuggestions);
        stockSearch.addEventListener('change', handleStockSelection);
    }
    
    // Instrument type selection event listener
    const instrumentType = document.getElementById('instrumentType');
    if (instrumentType) {
        instrumentType.addEventListener('change', updateSuggestions);
    }
    
    // API Token toggle event listener
    const toggleApiTokenBtn = document.getElementById('toggleApiToken');
    if (toggleApiTokenBtn) {
        toggleApiTokenBtn.addEventListener('click', () => togglePasswordVisibility('apiToken', 'toggleApiToken'));
    }
    
    // Save API Token event listener
    const saveApiTokenBtn = document.getElementById('saveApiToken');
    if (saveApiTokenBtn) {
        saveApiTokenBtn.addEventListener('click', saveApiToken);
    }
    
    // Refresh API Token event listener
    const refreshApiTokenBtn = document.getElementById('refreshApiToken');
    if (refreshApiTokenBtn) {
        refreshApiTokenBtn.addEventListener('click', refreshApiToken);
    }
    
    // Apply Supertrend button event listener
    const applySupertrendBtn = document.getElementById('applySupertrend');
    if (applySupertrendBtn) {
        applySupertrendBtn.addEventListener('click', handleSupertrendCalculation);
    }
    
    // Order form submission event listener
    const orderForm = document.getElementById('orderForm');
    if (orderForm) {
        orderForm.addEventListener('submit', handleOrderSubmit);
    }
});