/**
 * FilterBar Component
 *
 * Provides filtering and search controls for worker list.
 * Replaces scattered filter event listeners in workers.js.
 *
 * Usage:
 *   <filter-bar></filter-bar>
 */

import { BaseComponent } from '../core/BaseComponent.js';
import { EventTypes } from '../core/EventBus.js';

export class FilterBar extends BaseComponent {
    static get observedAttributes() {
        return ['view', 'is-admin'];
    }

    constructor() {
        super();
    }

    onMount() {
        this.render();
        this.attachEventListeners();
    }

    onAttributeChange(name, oldValue, newValue) {
        if (name === 'view' && oldValue !== newValue) {
            const select = this.$('#view-toggle');
            if (select) {
                select.value = newValue;
            }
        }
    }

    render() {
        const currentView = this.getAttr('view') || 'cards';
        const isAdmin = this.getAttr('is-admin') === 'true';

        this.innerHTML = `
            <div class="filter-bar mb-3">
                <div class="row g-3">
                    <div class="col-md-3">
                        <label for="filter-region" class="form-label">Region</label>
                        <select id="filter-region" class="form-select">
                            <option value="us-east-1">US East (N. Virginia)</option>
                            <option value="us-west-2">US West (Oregon)</option>
                            <option value="eu-west-1">EU (Ireland)</option>
                            <option value="ap-southeast-1">Asia Pacific (Singapore)</option>
                        </select>
                    </div>
                    <div class="col-md-3">
                        <label for="filter-status" class="form-label">Status</label>
                        <select id="filter-status" class="form-select">
                            <option value="all">All Statuses</option>
                            <option value="running">Running</option>
                            <option value="stopped">Stopped</option>
                            <option value="stopping">Stopping</option>
                            <option value="pending">Pending</option>
                            <option value="terminated">Terminated</option>
                        </select>
                        ${
                            isAdmin
                                ? `
                        <div class="form-check mt-2">
                            <input class="form-check-input" type="checkbox" id="include-terminated">
                            <label class="form-check-label" for="include-terminated">
                                Include Terminated
                            </label>
                        </div>
                        `
                                : ''
                        }
                    </div>
                    <div class="col-md-4">
                        <label for="search-workers" class="form-label">Search</label>
                        <input
                            type="text"
                            id="search-workers"
                            class="form-control"
                            placeholder="Search by name, region, or instance ID..."
                        >
                    </div>
                    <div class="col-md-2">
                        <label for="view-toggle" class="form-label">View</label>
                        <select id="view-toggle" class="form-select">
                            <option value="cards" ${currentView === 'cards' ? 'selected' : ''}>Cards</option>
                            <option value="table" ${currentView === 'table' ? 'selected' : ''}>Table</option>
                        </select>
                    </div>
                </div>
            </div>
        `;
    }

    attachEventListeners() {
        const regionSelect = this.$('#filter-region');
        const statusSelect = this.$('#filter-status');
        const searchInput = this.$('#search-workers');
        const viewSelect = this.$('#view-toggle');
        const includeTerminatedCheckbox = this.$('#include-terminated');

        if (regionSelect) {
            regionSelect.addEventListener('change', e => {
                this.emit(EventTypes.UI_FILTER_CHANGED, {
                    type: 'region',
                    value: e.target.value,
                });
            });
        }

        if (statusSelect) {
            statusSelect.addEventListener('change', e => {
                this.emit(EventTypes.UI_FILTER_CHANGED, {
                    type: 'status',
                    value: e.target.value,
                });
            });
        }

        if (includeTerminatedCheckbox) {
            includeTerminatedCheckbox.addEventListener('change', e => {
                this.emit(EventTypes.UI_FILTER_CHANGED, {
                    type: 'include_terminated',
                    value: e.target.checked,
                });
            });
        }

        if (searchInput) {
            const debouncedSearch = this.debounce(e => {
                this.emit(EventTypes.UI_FILTER_CHANGED, {
                    type: 'search',
                    value: e.target.value,
                });
            }, 300);

            searchInput.addEventListener('input', debouncedSearch);
        }

        if (viewSelect) {
            viewSelect.addEventListener('change', e => {
                this.emit(EventTypes.UI_FILTER_CHANGED, {
                    type: 'view',
                    value: e.target.value,
                });
            });
        }
    }
}

// Register custom element
customElements.define('filter-bar', FilterBar);

export default FilterBar;
