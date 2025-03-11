// Function to test API connection
function testApiConnection(digikeyNumber) {
    if (!digikeyNumber || digikeyNumber.trim() === '') {
        alert('Please enter a DigiKey number');
        return;
    }
    
    // Show loading status
    const apiTestButton = document.querySelector('button[onclick*="testApiConnection"]');
    if (apiTestButton) {
        const originalText = apiTestButton.innerHTML;
        apiTestButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Testing API...';
        apiTestButton.disabled = true;
        
        // Reset after 30 seconds if no response
        const resetTimeout = setTimeout(() => {
            apiTestButton.innerHTML = originalText;
            apiTestButton.disabled = false;
            alert('API request timeout. Please try again later.');
        }, 30000);

        fetch('/test_api/' + encodeURIComponent(digikeyNumber))
            .then(response => {
                clearTimeout(resetTimeout);
                if (!response.ok) {
                    throw new Error('Network response was not ok: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                apiTestButton.innerHTML = originalText;
                apiTestButton.disabled = false;
                
                if (data.error) {
                    alert('API Error: ' + data.error);
                } else {
                    alert('API Test Result:\n' + 
                        'Description: ' + (data.description || 'Not available') + '\n' +
                        'Manufacturer Part Number: ' + (data.manufacturer_part_number || 'Not available'));
                }
            })
            .catch(error => {
                clearTimeout(resetTimeout);
                apiTestButton.innerHTML = originalText;
                apiTestButton.disabled = false;
                console.error('API Error:', error);
                alert('API Error: ' + error.message);
            });
    } else {
        // Fallback if button not found
        fetch('/test_api/' + encodeURIComponent(digikeyNumber))
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                if (data.error) {
                    alert('API Error: ' + data.error);
                } else {
                    alert('API Test Result:\n' + 
                        'Description: ' + (data.description || 'Not available') + '\n' +
                        'Manufacturer Part Number: ' + (data.manufacturer_part_number || 'Not available'));
                }
            })
            .catch(error => {
                console.error('API Error:', error);
                alert('API Error: ' + error.message);
            });
    }
}

// Monitor upload progress
function monitorUploadProgress(trackingId) {
    if (!trackingId) return;
    
    const progressContainer = document.getElementById('upload-progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressMessage = document.getElementById('progress-message');
    const progressDetails = document.getElementById('progress-details');
    const failedPartsContainer = document.getElementById('failed-parts-container');
    const failedPartsList = document.getElementById('failed-parts-list');
    const closeProgressContainerBtn = document.getElementById('close-progress-container');
    
    if (!progressContainer || !progressBar || !progressMessage) return;
    
    // Clear any existing check intervals to prevent duplicates
    if (window.progressCheckInterval) {
        clearInterval(window.progressCheckInterval);
    }
    
    // Initialize progress bar
    progressBar.style.width = '0%';
    progressBar.innerText = '0%';
    progressMessage.innerText = 'Initializing import...';
    
    // Event handler for closing the entire progress container
    if (closeProgressContainerBtn) {
        closeProgressContainerBtn.addEventListener('click', function() {
            // Clear the interval to stop progress checking
            if (window.progressCheckInterval) {
                clearInterval(window.progressCheckInterval);
                window.progressCheckInterval = null;
            }
            
            // Hide the container
            progressContainer.style.display = 'none';
            
            // Remove the tracking ID from the URL to prevent reloading the progress
            const currentUrl = new URL(window.location.href);
            currentUrl.searchParams.delete('tracking_id');
            window.history.replaceState({}, document.title, currentUrl.toString());
            
            // Reload the page without the tracking ID
            window.location.href = currentUrl.toString();
        });
    }
    
    // Interval for progress polling
    window.progressCheckInterval = setInterval(() => {
        fetch('/import-progress/' + trackingId)
            .then(response => response.json())
            .then(data => {
                // Update progress bar
                progressBar.style.width = data.progress + '%';
                progressBar.innerText = data.progress + '%';
                progressBar.setAttribute('aria-valuenow', data.progress);
                
                // Update status message
                progressMessage.innerText = data.message || 'Import in progress...';
                
                // Display details if available
                if (data.details) {
                    let detailsText = '';
                    if (data.details.total_parts && data.details.processed_parts) {
                        detailsText += `Processing: ${data.details.processed_parts} of ${data.details.total_parts} parts`;
                    }
                    progressDetails.innerText = detailsText;
                }
                
                // Color based on status
                if (data.status === 'error') {
                    progressBar.classList.remove('bg-info', 'bg-success');
                    progressBar.classList.add('bg-danger');
                    clearInterval(window.progressCheckInterval);
                    window.progressCheckInterval = null;
                } else if (data.status === 'completed') {
                    progressBar.classList.remove('bg-info', 'bg-danger');
                    progressBar.classList.add('bg-success');
                    
                    // Show failed parts if any
                    if (data.details && data.details.failed_parts && data.details.failed_parts.length > 0) {
                        failedPartsList.innerHTML = '';
                        
                        data.details.failed_parts.forEach(part => {
                            const listItem = document.createElement('li');
                            listItem.innerHTML = `<strong>${part.digikey_number}</strong>: ${part.error}`;
                            failedPartsList.appendChild(listItem);
                        });
                        
                        failedPartsContainer.style.display = 'block';
                    }
                    
                    // End interval when finished
                    clearInterval(window.progressCheckInterval);
                    window.progressCheckInterval = null;
                }
            })
            .catch(error => {
                console.error('Error fetching progress:', error);
            });
    }, 1000);
    
    // Timeout after 5 minutes if no completion message
    setTimeout(() => {
        if (window.progressCheckInterval) {
            clearInterval(window.progressCheckInterval);
            window.progressCheckInterval = null;
            progressMessage.innerText = 'Timeout - Please reload the page to see current status.';
        }
    }, 5 * 60 * 1000);
}

// Debounce function to limit API calls
function debounce(func, wait) {
    let timeout;
    return function() {
        const context = this;
        const args = arguments;
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            func.apply(context, args);
        }, wait);
    };
}

// Event-Handler-Safety Function
function safeQuerySelector(selector, callback) {
    const element = document.querySelector(selector);
    if (element) {
        callback(element);
    }
    return element;
}

// Event-Handler-Safety Function for multiple elements
function safeQuerySelectorAll(selector, callback) {
    const elements = document.querySelectorAll(selector);
    if (elements && elements.length > 0) {
        callback(elements);
    }
    return elements;
}

/**
 * Safe event handler addition
 * @param {HTMLElement} element - The DOM element
 * @param {string} eventType - The event type (click, change, etc.)
 * @param {Function} callback - The callback function
 */
function addSafeEventListener(element, eventType, callback) {
    if (element) {
        element.addEventListener(eventType, callback);
    }
}

/**
 * Format error messages
 * @param {string|Error} error - The error message or Error object
 */
function formatError(error) {
    if (error instanceof Error) {
        return error.message;
    }
    return String(error);
}

document.addEventListener('DOMContentLoaded', function() {
    // BOM upload form intercept and pass tracking_id
    safeQuerySelector('#bom-import-form', form => {
        addSafeEventListener(form, 'submit', function(event) {
            const fileInput = document.getElementById('file');
            if (!fileInput || !fileInput.files || !fileInput.files[0]) {
                alert('Please select a CSV file.');
                event.preventDefault();
                return;
            }
            
            // Update UI status
            const uploadButton = document.getElementById('bom-upload-btn');
            if (uploadButton) {
                uploadButton.disabled = true;
                uploadButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Uploading file...';
            }
        });
    });
    
    // Start progress tracking if a tracking_id is present
    const progressContainer = document.getElementById('upload-progress-container');
    if (progressContainer) {
        const trackingId = progressContainer.dataset.trackingId;
        if (trackingId) {
            monitorUploadProgress(trackingId);
        }
    }
    
    // Toggle for delete mode
    safeQuerySelector('#delete-mode-switch', deleteSwitch => {
        safeQuerySelector('.delete-mode-label', deleteLabel => {
            safeQuerySelectorAll('.delete-part-btn', deleteButtons => {
                addSafeEventListener(deleteSwitch, 'change', function() {
                    if (this.checked) {
                        // Enable delete function
                        deleteLabel.textContent = 'Delete function enabled';
                        deleteLabel.style.color = 'red';
                        // Enable all delete buttons
                        deleteButtons.forEach(button => {
                            button.disabled = false;
                        });
                    } else {
                        // Disable delete function
                        deleteLabel.textContent = 'Delete function disabled';
                        deleteLabel.style.color = '';
                        // Disable all delete buttons
                        deleteButtons.forEach(button => {
                            button.disabled = true;
                        });
                    }
                });
            });
        });
    });

    // Event handlers for delete buttons
    safeQuerySelectorAll('.delete-part-btn', deleteButtons => {
        deleteButtons.forEach(button => {
            addSafeEventListener(button, 'click', function() {
                if (this.disabled) return; // Skip if button is disabled
                
                const partId = this.dataset.partId;
                if (!partId) return;
                
                if (confirm('Are you sure you want to delete this component?')) {
                    // Show loading status
                    const originalInnerHTML = this.innerHTML;
                    this.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                    this.disabled = true;
                    
                    fetch('/delete_part/' + partId, {
                        method: 'POST',
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest'
                        }
                    })
                    .then(response => {
                        if (!response.ok) {
                            throw new Error('Network response was not ok: ' + response.status);
                        }
                        return response.json();
                    })
                    .then(data => {
                        if (data.success) {
                            // Remove the row from the table
                            const row = document.querySelector(`tr[data-part-id="${partId}"]`);
                            if (row) {
                                row.remove();
                                
                                // Update display statistics
                                safeQuerySelector('#filtered-count', filteredCount => {
                                    const currentCount = parseInt(filteredCount.textContent, 10);
                                    if (!isNaN(currentCount)) {
                                        filteredCount.textContent = (currentCount - 1).toString();
                                    }
                                });
                                
                                safeQuerySelector('.component-count span:last-child', totalCount => {
                                    const currentTotal = parseInt(totalCount.textContent, 10);
                                    if (!isNaN(currentTotal)) {
                                        totalCount.textContent = (currentTotal - 1).toString();
                                    }
                                });
                            } else {
                                // If row not found, reload page
                                window.location.reload();
                            }
                        } else {
                            alert('Error deleting: ' + (data.message || 'Unknown error'));
                            // Reset button
                            this.innerHTML = originalInnerHTML;
                            this.disabled = false;
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('An error occurred: ' + formatError(error));
                        // Reset button
                        this.innerHTML = originalInnerHTML;
                        this.disabled = false;
                    });
                }
            });
        });
    });
    
    // Initialize Select2 for multiple selection, if jQuery and Select2 are available
    if (typeof $ !== 'undefined' && $.fn && $.fn.select2) {
        safeQuerySelector('#usage', element => {
            $(element).select2({
                placeholder: 'Select devices',
                allowClear: true,
                width: '100%'
            });
        });
        
        safeQuerySelector('#add_usage_device', element => {
            $(element).select2({
                dropdownParent: $('#addUsageModal'),
                placeholder: 'Select device',
                width: '100%'
            });
        });
    }
    
    // JavaScript for the search with type dropdown
    const partSearchInput = document.getElementById('part_search');
    const searchTypeSelect = document.getElementById('search_type');
    const matchingPartSelect = document.getElementById('matching_part');
    const partNumberInput = document.getElementById('part_number');
    const digikeyNumberInput = document.getElementById('digikey_number');
    const descriptionInput = document.getElementById('description');
    const matchTypeHint = document.getElementById('match_type_hint');
    const clearSearchBtn = document.getElementById('clear-part-search');
    
    // Clear function
    if (clearSearchBtn) {
        addSafeEventListener(clearSearchBtn, 'click', function() {
            if (partSearchInput) partSearchInput.value = '';
            resetMatchingParts();
            if (partNumberInput) partNumberInput.value = '';
            if (digikeyNumberInput) digikeyNumberInput.value = '';
            if (descriptionInput) descriptionInput.value = '';
            if (partSearchInput) partSearchInput.focus();
        });
    }
    
    // Function to reset the dropdown list
    function resetMatchingParts() {
        if (matchingPartSelect) {
            matchingPartSelect.innerHTML = '<option value="" selected>First search for a part number</option>';
        }
        if (matchTypeHint) {
            matchTypeHint.textContent = 'After searching, you can select a matching part number';
        }
    }
    
    // Search for parts based on input and selected type
    if (partSearchInput && searchTypeSelect) {
        addSafeEventListener(partSearchInput, 'input', debounce(function() {
            searchForParts();
        }, 500));
        
        // Also search again when search type changes
        addSafeEventListener(searchTypeSelect, 'change', function() {
            if (partSearchInput.value.trim().length >= 3) {
                searchForParts();
            }
        });
    }
    
    // Function to search for parts
    function searchForParts() {
        if (!partSearchInput || !searchTypeSelect || !matchingPartSelect || !matchTypeHint) {
            console.error('One or more required elements are missing');
            return;
        }
        
        const searchTerm = partSearchInput.value.trim();
        
        if (searchTerm.length < 3) {
            resetMatchingParts();
            return;
        }
        
        // Get search type from dropdown
        const isDKNumber = searchTypeSelect.value === 'dk';
        
        // Show loading indicator
        matchingPartSelect.innerHTML = '<option value="" selected>Searching...</option>';
        
        fetch('/search_digikey_by_mpn/' + encodeURIComponent(searchTerm))
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                console.log("API response received:", data);
                
                // Reset dropdown
                resetMatchingParts();
                
                if (!data || data.length === 0 || data.error) {
                    matchingPartSelect.innerHTML = '<option value="" selected>No results found</option>';
                    if (data && data.error) {
                        console.error('API Error:', data.error);
                    }
                } else {
                    // Based on selected search type, adjust hint text
                    if (isDKNumber) {
                        matchTypeHint.textContent = 'DigiKey number search. Select the matching Manufacturer Part Number.';
                    } else {
                        matchTypeHint.textContent = 'Manufacturer Part Number search. Select the matching DigiKey number.';
                    }
                    
                    // Add results to dropdown
                    data.forEach(item => {
                        // Ensure required fields are present
                        if (!item.digikey_number || !item.part_number) {
                            return;
                        }
                        
                        // Check if response matches search type
                        let isRelevant = true;
                        
                        if (isDKNumber && !item.digikey_number.includes(searchTerm) && item.digikey_number.toLowerCase() !== searchTerm.toLowerCase()) {
                            isRelevant = false;
                        } else if (!isDKNumber && !item.part_number.includes(searchTerm) && item.part_number.toLowerCase() !== searchTerm.toLowerCase()) {
                            isRelevant = false;
                        }
                        
                        if (isRelevant) {
                            const option = document.createElement('option');
                            // Store value in format "mpn|||dkn|||description" so we have all info
                            option.value = `${item.part_number}|||${item.digikey_number}|||${item.description || ''}`;
                            
                            // Display based on selected search type
                            if (isDKNumber) {
                                // If searching by DigiKey number, show manufacturer number
                                option.textContent = `${item.part_number} (${item.description || 'No description'})`;
                            } else {
                                // If searching by manufacturer number, show DigiKey number
                                option.textContent = `${item.digikey_number} (${item.description || 'No description'})`;
                            }
                            
                            matchingPartSelect.appendChild(option);
                            
                            // If exact match, auto-select
                            if ((isDKNumber && item.digikey_number === searchTerm) || 
                                (!isDKNumber && item.part_number === searchTerm)) {
                                option.selected = true;
                                // Also populate hidden fields
                                updateHiddenFields(option.value);
                            }
                        }
                    });
                    
                    // Check if any matching entries were added
                    if (matchingPartSelect.options.length <= 1) {
                        matchingPartSelect.innerHTML = '<option value="" selected>No matching results found</option>';
                    }
                }
            })
            .catch(error => {
                console.error('Search error:', error);
                matchingPartSelect.innerHTML = '<option value="" selected>Search error</option>';
                matchTypeHint.textContent = 'Error: ' + formatError(error);
            });
    }
    
    // Event handler for selecting an option in the results dropdown
    if (matchingPartSelect) {
        addSafeEventListener(matchingPartSelect, 'change', function() {
            const selectedValue = this.value;
            if (selectedValue) {
                updateHiddenFields(selectedValue);
            } else {
                // Nothing selected, clear fields
                if (partNumberInput) partNumberInput.value = '';
                if (digikeyNumberInput) digikeyNumberInput.value = '';
                if (descriptionInput) descriptionInput.value = '';
            }
        });
    }
    
    // Function to update hidden fields and description
    function updateHiddenFields(value) {
        if (!partNumberInput || !digikeyNumberInput || !descriptionInput) {
            console.error('One or more required fields are missing');
            return;
        }
        
        // Format is "mpn|||dkn|||description"
        const parts = value.split('|||');
        if (parts.length >= 3) {
            partNumberInput.value = parts[0] || '';
            digikeyNumberInput.value = parts[1] || '';
            descriptionInput.value = parts[2] || '';
        }
    }
    
    // Quantity specification for selected devices in Add-Part-Form
    const usageSelect = document.getElementById('usage');
    const usageQuantitiesDiv = document.getElementById('usage-quantities');
    const deviceQuantityInputsDiv = document.getElementById('device-quantity-inputs');

    if (usageSelect && usageQuantitiesDiv && deviceQuantityInputsDiv && typeof $ !== 'undefined') {
        // Event listener for changes in the Select2 dropdown
        $(usageSelect).on('change', function() {
            const selectedDevices = $(this).val();
            
            if (selectedDevices && selectedDevices.length > 0) {
                // Show quantity area
                usageQuantitiesDiv.style.display = 'block';
                
                // Create input fields for quantities
                deviceQuantityInputsDiv.innerHTML = '';
                
                selectedDevices.forEach(deviceId => {
                    // Ensure the selected element exists
                    const option = $(usageSelect).find(`option[value="${deviceId}"]`);
                    if (option.length === 0) return;
                    
                    const deviceName = option.text();
                    
                    const deviceInputGroup = document.createElement('div');
                    deviceInputGroup.className = 'input-group mb-2';
                    
                    const deviceLabel = document.createElement('span');
                    deviceLabel.className = 'input-group-text';
                    deviceLabel.style.width = '200px'; // Fixed width for better alignment
                    deviceLabel.style.overflow = 'hidden';
                    deviceLabel.style.textOverflow = 'ellipsis';
                    deviceLabel.title = deviceName;
                    deviceLabel.textContent = deviceName;
                    
                    const quantityInput = document.createElement('input');
                    quantityInput.type = 'number';
                    quantityInput.className = 'form-control device-qty-input';
                    quantityInput.name = `device_qty_${deviceId}`;
                    quantityInput.min = '1';
                    quantityInput.value = '1';
                    quantityInput.required = true;
                    quantityInput.setAttribute('data-device-id', deviceId);
                    
                    deviceInputGroup.appendChild(deviceLabel);
                    deviceInputGroup.appendChild(quantityInput);
                    
                    deviceQuantityInputsDiv.appendChild(deviceInputGroup);
                });
            } else {
                // No devices selected, hide quantity area
                usageQuantitiesDiv.style.display = 'none';
                deviceQuantityInputsDiv.innerHTML = '';
            }
        });
        
        // Add-Part-Form handler adjustment
        const addPartForm = document.getElementById('add-part-form');
        if (addPartForm) {
            addSafeEventListener(addPartForm, 'submit', function(event) {
                // Keep existing validation
                if ((!digikeyNumberInput || !digikeyNumberInput.value) || 
                    (!partNumberInput || !partNumberInput.value)) {
                    event.preventDefault();
                    alert('Please select a valid part number from the dropdown list.');
                    return;
                }
                
                // Collect quantities for each selected device
                const deviceQuantities = {};
                const quantityInputs = document.querySelectorAll('.device-qty-input');
                
                let hasInvalidQuantity = false;
                
                if (quantityInputs) {
                    quantityInputs.forEach(input => {
                        if (!input) return;
                        
                        const deviceId = input.getAttribute('data-device-id');
                        if (!deviceId) return;
                        
                        const quantity = parseInt(input.value, 10) || 1; // Default to 1 if invalid
                        
                        if (quantity < 1) {
                            hasInvalidQuantity = true;
                            input.classList.add('is-invalid');
                        } else {
                            input.classList.remove('is-invalid');
                            deviceQuantities[deviceId] = quantity;
                        }
                    });
                }
                
                if (hasInvalidQuantity) {
                    event.preventDefault();
                    alert('Quantity must be at least 1.');
                    return;
                }
                
                // Store quantities in a hidden field
                const deviceQuantitiesField = document.createElement('input');
                deviceQuantitiesField.type = 'hidden';
                deviceQuantitiesField.name = 'device_quantities';
                deviceQuantitiesField.value = JSON.stringify(deviceQuantities);
                this.appendChild(deviceQuantitiesField);
            });
        }
    }
    
    // Filtering and searching
    const searchInput = document.getElementById('search-input');
    const modelSelectors = document.querySelectorAll('.model-selector');
    const tableRows = document.querySelectorAll('#inventory-table tbody tr');
    
    if (searchInput && modelSelectors.length > 0 && tableRows.length > 0) {
        // Search function
        addSafeEventListener(searchInput, 'input', filterTable);
        
        // Model filter with multiple selection
        modelSelectors.forEach(selector => {
            if (selector) {
                addSafeEventListener(selector, 'click', function(event) {
                    // With Ctrl key pressed, multiple devices can be selected
                    if (!event.ctrlKey && !event.metaKey) {
                        // Without Ctrl/Cmd key: Reset all selections
                        modelSelectors.forEach(s => {
                            if (s !== this) s.classList.remove('active');
                        });
                    }
                    
                    // Toggle current selection
                    this.classList.toggle('active');
                    
                    // If no selection is active, select "All"
                    const hasActive = Array.from(modelSelectors).some(s => s.classList.contains('active'));
                    if (!hasActive) {
                        const allSelector = document.querySelector('.model-selector[data-model="all"]');
                        if (allSelector) {
                            allSelector.classList.add('active');
                        }
                    }
                    
                    // Filter table
                    filterTable();
                });
            }
        });
        
        // Filter function
        function filterTable() {
            const searchTerm = searchInput.value.toLowerCase();
            
            // Collect all active filters
            const activeSelectors = document.querySelectorAll('.model-selector.active');
            if (!activeSelectors) return;
            
            const activeModels = Array.from(activeSelectors)
                .map(selector => selector.dataset.model || '');
            
            // "All" is always included if nothing else is selected
            const filterAll = activeModels.includes('all') || activeModels.length === 0;
            // Check if "Unassigned" is active
            const filterUnassigned = activeModels.includes('unassigned');
            
            let visibleCount = 0;
            
            tableRows.forEach(row => {
                if (!row) return;
                
                const partNumberCell = row.querySelector('td:nth-child(1)');
                const digikeyNumberCell = row.querySelector('td:nth-child(2)');
                const descriptionCell = row.querySelector('td:nth-child(3)');
                
                if (!partNumberCell || !digikeyNumberCell || !descriptionCell) return;
                
                const partNumber = partNumberCell.textContent.toLowerCase();
                const digikeyNumber = digikeyNumberCell.textContent.toLowerCase();
                const description = descriptionCell.textContent.toLowerCase();
                
                // Check search criteria
                const matchesSearch = partNumber.includes(searchTerm) || 
                                    digikeyNumber.includes(searchTerm) || 
                                    description.includes(searchTerm);
                
                // Check model filter - with multiple active filters, it's enough if one matches
                let matchesModel = filterAll; // "All" always matches
                
                // Check usages from the Usage column
                const usageColumn = row.querySelector('td:nth-child(5)');  // After removing the Required column, Usage is now at position 5
                if (!usageColumn) return;
                
                // Check for unassigned parts
                const unassignedBadge = usageColumn.querySelector('.unassigned-badge');
                const isUnassigned = !!unassignedBadge;
                
                // If Unassigned is filtered and part is not assigned, show it
                if (filterUnassigned && isUnassigned) {
                    matchesModel = true;
                    if (unassignedBadge) {
                        unassignedBadge.style.display = '';
                    }
                } else if (isUnassigned && !filterUnassigned && !filterAll) {
                    // If filtering for a specific device but part is unassigned, hide
                    matchesModel = false;
                }
                
                // Check device badges from the Usage column
                const deviceBadges = usageColumn.querySelectorAll('.device-badge:not(.unassigned-badge)');
                
                // First reset all badges and show them
                deviceBadges.forEach(badge => {
                    if (!badge) return;
                    badge.style.display = '';
                    badge.classList.remove('active-filter');
                });
                
                if (!filterAll && !filterUnassigned) {
                    // If a specific filter is active
                    let hasMatchingBadge = false;
                    
                    // Check if one of the selected models is in the badges
                    deviceBadges.forEach(badge => {
                        if (!badge) return;
                        
                        const deviceId = badge.dataset.deviceId;
                        if (!deviceId) return;
                        
                        if (activeModels.includes(deviceId)) {
                            matchesModel = true;
                            hasMatchingBadge = true;
                            
                            // Mark this badge as part of the active filters
                            badge.classList.add('active-filter');
                            badge.style.display = ''; // Explicitly make visible
                        } else {
                            // If the device is not in the active filter, hide
                            badge.style.display = 'none';
                        }
                    });
                    
                    // If specific filter active and part has matching device badges, show
                    if (deviceBadges.length > 0) {
                        matchesModel = hasMatchingBadge;
                    }
                }
                
                // Set visibility
                if (matchesSearch && matchesModel) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });
            
            // Update visible components count
            safeQuerySelector('#filtered-count', filteredCount => {
                filteredCount.textContent = visibleCount;
            });
        }
    }

    // Edit stock directly
    safeQuerySelectorAll('.edit-stock-btn', editStockBtns => {
        editStockBtns.forEach(btn => {
            addSafeEventListener(btn, 'click', function() {
                const partId = this.dataset.partId;
                const currentQty = this.dataset.partQuantity;
                
                if (!partId) {
                    alert('Error: Component ID not found');
                    return;
                }
                
                // Input via prompt dialog
                const newQty = prompt('Enter new stock quantity:', currentQty);
                
                if (newQty !== null) {
                    // Only accept numeric values
                    if (!isNaN(newQty) && newQty.trim() !== '') {
                        // Prevent negative values
                        const qty = Math.max(0, parseInt(newQty, 10));
                        
                        // AJAX request to update stock
                        fetch('/update_stock', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded',
                                'X-Requested-With': 'XMLHttpRequest'
                            },
                            body: `part_id=${partId}&quantity=${qty}`
                        })
                        .then(response => {
                            if (!response.ok) {
                                throw new Error('Network response was not ok: ' + response.status);
                            }
                            return response.text();
                        })
                        .then(() => {
                            // Update stock in UI
                            safeQuerySelector(`.stock-qty-display[data-part-id="${partId}"]`, stockDisplay => {
                                stockDisplay.textContent = qty;
                                
                                // Change badge color based on quantity
                                if (qty == 0) {
                                    stockDisplay.classList.remove('bg-primary');
                                    stockDisplay.classList.add('bg-danger');
                                } else {
                                    stockDisplay.classList.remove('bg-danger');
                                    stockDisplay.classList.add('bg-primary');
                                }
                            });
                            
                            // Also update the button's data attribute
                            this.dataset.partQuantity = qty;
                            
                            // Update component status class (requires reload)
                            window.location.reload();
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            alert('Error updating stock: ' + formatError(error));
                        });
                    } else {
                        alert('Please enter a valid number.');
                    }
                }
            });
        });
    });

    // Delete function for devices
    safeQuerySelectorAll('.delete-device-btn', deleteDeviceBtns => {
        deleteDeviceBtns.forEach(btn => {
            addSafeEventListener(btn, 'click', function() {
                const deviceId = this.dataset.deviceId;
                const deviceName = this.dataset.deviceName;
                
                if (!deviceId || !deviceName) {
                    alert('Error: Device information not found');
                    return;
                }
                
                if (confirm(`Are you sure you want to delete the device "${deviceName}"? This action cannot be undone.`)) {
                    // Show loading status
                    const originalInnerHTML = this.innerHTML;
                    this.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                    this.disabled = true;
                    
                    fetch(`/delete_device/${deviceId}`, {
                        method: 'POST',
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest'
                        }
                    })
                    .then(response => {
                        if (!response.ok) {
                            throw new Error('Network response was not ok: ' + response.status);
                        }
                        return response.json();
                    })
                    .then(data => {
                        if (data.success) {
                            // Successful deletion
                            alert(data.message);
                            
                            // Remove device from the list
                            safeQuerySelector(`.device-row[data-device-id="${deviceId}"]`, deviceRow => {
                                deviceRow.remove();
                            });
                            
                            // Update device filter
                            safeQuerySelector(`.model-selector[data-model="${deviceId}"]`, modelSelector => {
                                if (modelSelector) {
                                    modelSelector.remove();
                                }
                            });
                            
                            // Reload page to update all references
                            window.location.reload();
                        } else {
                            alert('Error: ' + (data.message || 'Unknown error'));
                            // Reset button
                            this.innerHTML = originalInnerHTML;
                            this.disabled = false;
                        }
                    })
                    .catch(error => {
                        console.error('Error deleting device:', error);
                        alert('Error deleting device: ' + formatError(error));
                        // Reset button
                        this.innerHTML = originalInnerHTML;
                        this.disabled = false;
                    });
                }
            });
        });
    });

    // Initialize Bootstrap Tooltips, if available
    if (typeof bootstrap !== 'undefined' && typeof bootstrap.Tooltip !== 'undefined') {
        const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        if (tooltipTriggerList) {
            [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
        }
    }

    // Add a usage
    safeQuerySelectorAll('.add-usage-btn', addUsageBtns => {
        addUsageBtns.forEach(btn => {
            addSafeEventListener(btn, 'click', function() {
                const partId = this.dataset.partId;
                if (!partId) {
                    alert('Error: Component ID not found');
                    return;
                }
                
                // Set the part ID in the modal's hidden field
                safeQuerySelector('#add_usage_part_id', field => {
                    field.value = partId;
                });
                
                // Show the modal
                if (typeof bootstrap !== 'undefined' && typeof bootstrap.Modal !== 'undefined') {
                    const modalElement = document.getElementById('addUsageModal');
                    if (modalElement) {
                        const modal = new bootstrap.Modal(modalElement);
                        modal.show();
                    }
                }
            });
        });
    });

    // Save a new usage
    safeQuerySelector('#save_new_usage_btn', saveBtn => {
        addSafeEventListener(saveBtn, 'click', function() {
            const partId = document.getElementById('add_usage_part_id')?.value;
            const deviceSelect = document.getElementById('add_usage_device');
            const quantityInput = document.getElementById('add_usage_qty');
            
            if (!partId || !deviceSelect || !quantityInput) {
                alert('Error: Missing form elements');
                return;
            }
            
            const deviceId = deviceSelect.value;
            const quantity = parseInt(quantityInput.value, 10);
            
            if (!deviceId) {
                alert('Please select a device.');
                return;
            }
            
            if (isNaN(quantity) || quantity < 1) {
                alert('Please enter a valid quantity (minimum 1).');
                return;
            }
            
            // Show loading status
            const originalInnerHTML = this.innerHTML;
            this.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Saving...';
            this.disabled = true;
            
            // Send the data to the server
            fetch('/update_part_usage', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: `part_id=${partId}&device_id=${deviceId}&qty_required=${quantity}`
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Close the modal
                    if (typeof bootstrap !== 'undefined') {
                        const modalElement = document.getElementById('addUsageModal');
                        if (modalElement) {
                            bootstrap.Modal.getInstance(modalElement)?.hide();
                        }
                    }
                    
                    // Reload the page to update all related views
                    window.location.reload();
                } else {
                    alert('Error: ' + (data.message || 'Unknown error'));
                    // Reset button
                    this.innerHTML = originalInnerHTML;
                    this.disabled = false;
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('An error occurred: ' + formatError(error));
                // Reset button
                this.innerHTML = originalInnerHTML;
                this.disabled = false;
            });
        });
    });
    
    // Add new device
    safeQuerySelector('#add_device_btn', addDeviceBtn => {
        addSafeEventListener(addDeviceBtn, 'click', function() {
            const deviceNameInput = document.getElementById('new_device_name');
            if (!deviceNameInput) {
                alert('Error: Device name input not found');
                return;
            }
            
            const deviceName = deviceNameInput.value.trim();
            if (!deviceName) {
                alert('Please enter a device name.');
                return;
            }
            
            // Show loading status
            const originalInnerHTML = this.innerHTML;
            this.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Saving...';
            this.disabled = true;
            
            fetch('/add_device', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: `device_name=${encodeURIComponent(deviceName)}`
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Close the modal
                    if (typeof bootstrap !== 'undefined') {
                        const modalElement = document.getElementById('newDeviceModal');
                        if (modalElement) {
                            bootstrap.Modal.getInstance(modalElement)?.hide();
                        }
                    }
                    
                    // Update device lists
                    const usageSelect = document.getElementById('usage');
                    if (usageSelect) {
                        const option = document.createElement('option');
                        option.value = data.device_id;
                        option.textContent = data.device_name;
                        usageSelect.appendChild(option);
                        
                        // If using Select2, update Select2
                        if (typeof $ !== 'undefined' && $.fn && $.fn.select2) {
                            $(usageSelect).trigger('change');
                        }
                    }
                    
                    // Reset form
                    deviceNameInput.value = '';
                    
                    // Show success message
                    alert(`Device "${data.device_name}" successfully added.`);
                    
                    // Optional: Reload page
                    window.location.reload();
                } else {
                    alert('Error: ' + (data.message || 'Unknown error'));
                }
                
                // Reset button
                this.innerHTML = originalInnerHTML;
                this.disabled = false;
            })
            .catch(error => {
                console.error('Error:', error);
                alert('An error occurred: ' + formatError(error));
                // Reset button
                this.innerHTML = originalInnerHTML;
                this.disabled = false;
            });
        });
    });
    
    // Change model for missing parts analysis
    safeQuerySelector('#missing-parts-model', modelSelect => {
        addSafeEventListener(modelSelect, 'change', function() {
            const showMissingPartsBtn = document.getElementById('show-missing-parts');
            if (showMissingPartsBtn) {
                // Enable button only if a model is selected
                showMissingPartsBtn.disabled = !this.value;
            }
        });
    });
    
    // Show missing parts
    safeQuerySelector('#show-missing-parts', showMissingPartsBtn => {
        addSafeEventListener(showMissingPartsBtn, 'click', function() {
            const modelSelect = document.getElementById('missing-parts-model');
            if (!modelSelect) {
                alert('Error: Model selection not found');
                return;
            }
            
            const deviceId = modelSelect.value;
            if (!deviceId) {
                alert('Please select a hardware model.');
                return;
            }
            
            // Show loading status
            const originalInnerHTML = this.innerHTML;
            this.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Loading data...';
            this.disabled = true;
            
            fetch(`/missing_parts/${deviceId}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok: ' + response.status);
                    }
                    return response.json();
                })
                .then(data => {
                    // Reset button
                    this.innerHTML = originalInnerHTML;
                    this.disabled = false;
                    
                    // Show results
                    safeQuerySelector('#model-name', modelNameElement => {
                        modelNameElement.textContent = data.device_name;
                    });
                    
                    safeQuerySelector('#missing-parts-body', tableBody => {
                        tableBody.innerHTML = '';
                        
                        if (data.missing_parts && data.missing_parts.length > 0) {
                            data.missing_parts.forEach(part => {
                                const row = document.createElement('tr');
                                row.innerHTML = `
                                    <td>${part.part_number}</td>
                                    <td>${part.description}</td>
                                    <td class="text-center">${part.required}</td>
                                    <td class="text-center">${part.available}</td>
                                    <td class="text-center text-danger">${part.missing}</td>
                                `;
                                tableBody.appendChild(row);
                            });
                        } else {
                            // No missing parts
                            const row = document.createElement('tr');
                            row.innerHTML = `
                                <td colspan="5" class="text-center">No missing parts for this model.</td>
                            `;
                            tableBody.appendChild(row);
                        }
                    });
                    
                    safeQuerySelector('#missing-parts-container', container => {
                        container.style.display = 'block';
                    });
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Error loading missing parts: ' + formatError(error));
                    // Reset button
                    this.innerHTML = originalInnerHTML;
                    this.disabled = false;
                });
        });
    });
    
    // Event handlers for Device Badges
    safeQuerySelectorAll('.device-badge', deviceBadges => {
        deviceBadges.forEach(badge => {
            if (!badge.classList.contains('unassigned-badge')) {
                addSafeEventListener(badge, 'click', function() {
                    const partId = this.dataset.partId;
                    const deviceId = this.dataset.deviceId;
                    const deviceName = this.dataset.deviceName;
                    const qty = this.dataset.qty;
                    
                    if (!partId || !deviceId || !deviceName) {
                        alert('Error: Missing data for device or component');
                        return;
                    }
                    
                    // Populate modal fields
                    safeQuerySelector('#edit_usage_part_id', field => { field.value = partId; });
                    safeQuerySelector('#edit_usage_device_id', field => { field.value = deviceId; });
                    safeQuerySelector('#edit_usage_qty', field => { field.value = qty || 1; });
                    
                    // Display device name
                    safeQuerySelector('#editUsageModal .device-name-display', nameDisplay => {
                        nameDisplay.textContent = deviceName;
                    });
                    
                    // Show modal
                    if (typeof bootstrap !== 'undefined' && typeof bootstrap.Modal !== 'undefined') {
                        const modalElement = document.getElementById('editUsageModal');
                        if (modalElement) {
                            const modal = new bootstrap.Modal(modalElement);
                            modal.show();
                        }
                    }
                });
            }
        });
    });
    
    // Save an edited usage
    safeQuerySelector('#update_usage_btn', updateBtn => {
        addSafeEventListener(updateBtn, 'click', function() {
            const partId = document.getElementById('edit_usage_part_id')?.value;
            const deviceId = document.getElementById('edit_usage_device_id')?.value;
            const quantityInput = document.getElementById('edit_usage_qty');
            
            if (!partId || !deviceId || !quantityInput) {
                alert('Error: Missing form elements');
                return;
            }
            
            const quantity = parseInt(quantityInput.value, 10);
            
            if (isNaN(quantity) || quantity < 1) {
                alert('Please enter a valid quantity (minimum 1).');
                return;
            }
            
            // Show loading status
            const originalInnerHTML = this.innerHTML;
            this.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Saving...';
            this.disabled = true;
            
            fetch('/update_part_usage', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: `part_id=${partId}&device_id=${deviceId}&qty_required=${quantity}`
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Close modal
                    if (typeof bootstrap !== 'undefined') {
                        const modalElement = document.getElementById('editUsageModal');
                        if (modalElement) {
                            bootstrap.Modal.getInstance(modalElement)?.hide();
                        }
                    }
                    
                    // Update badge in the table
                    safeQuerySelector(`.device-badge[data-part-id="${partId}"][data-device-id="${deviceId}"] .device-qty`, qtyDisplay => {
                        qtyDisplay.textContent = quantity;
                    });
                    
                    // Update attribute
                    safeQuerySelector(`.device-badge[data-part-id="${partId}"][data-device-id="${deviceId}"]`, badge => {
                        badge.dataset.qty = quantity;
                    });
                    
                    // Reload page to update all views
                    window.location.reload();
                } else {
                    alert('Error: ' + (data.message || 'Unknown error'));
                }
                
                // Reset button
                this.innerHTML = originalInnerHTML;
                this.disabled = false;
            })
            .catch(error => {
                console.error('Error:', error);
                alert('An error occurred: ' + formatError(error));
                // Reset button
                this.innerHTML = originalInnerHTML;
                this.disabled = false;
            });
        });
    });
    
    // Remove a usage
    safeQuerySelector('#remove_usage_btn', removeBtn => {
        addSafeEventListener(removeBtn, 'click', function() {
            const partId = document.getElementById('edit_usage_part_id')?.value;
            const deviceId = document.getElementById('edit_usage_device_id')?.value;
            
            if (!partId || !deviceId) {
                alert('Error: Missing form elements');
                return;
            }
            
            if (confirm('Do you really want to remove this usage?')) {
                // Show loading status
                const originalInnerHTML = this.innerHTML;
                this.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Removing...';
                this.disabled = true;
                
                fetch('/update_part_usage', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: `part_id=${partId}&device_id=${deviceId}&qty_required=0`
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok: ' + response.status);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        // Close modal
                        if (typeof bootstrap !== 'undefined') {
                            const modalElement = document.getElementById('editUsageModal');
                            if (modalElement) {
                                bootstrap.Modal.getInstance(modalElement)?.hide();
                            }
                        }
                        
                        // Remove badge from table
                        safeQuerySelector(`.device-badge[data-part-id="${partId}"][data-device-id="${deviceId}"]`, badge => {
                            if (badge) {
                                badge.remove();
                            }
                        });
                        
                        // Reload page to update all views
                        window.location.reload();
                    } else {
                        alert('Error: ' + (data.message || 'Unknown error'));
                    }
                    
                    // Reset button
                    this.innerHTML = originalInnerHTML;
                    this.disabled = false;
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('An error occurred: ' + formatError(error));
                    // Reset button
                    this.innerHTML = originalInnerHTML;
                    this.disabled = false;
                });
            }
        });
    });
    
    // Check initially if a model-dependent button needs to be disabled
    safeQuerySelector('#missing-parts-model', modelSelect => {
        if (modelSelect) {
            safeQuerySelector('#show-missing-parts', showMissingPartsBtn => {
                if (showMissingPartsBtn) {
                    showMissingPartsBtn.disabled = !modelSelect.value;
                }
            });
        }
    });
});